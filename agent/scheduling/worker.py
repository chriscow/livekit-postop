"""
RQ Worker setup and management for PostOp AI call scheduling system
"""
import logging
import signal
import sys
import time
from datetime import datetime, timedelta
from typing import Optional

import redis
from rq import Worker, Queue
from rq.job import Job
from rq_scheduler import Scheduler

from .tasks import process_pending_calls
from .scheduler import CallScheduler

logger = logging.getLogger("scheduling-worker")


class PostOpCallWorker:
    """
    Manages RQ workers for executing scheduled follow-up calls
    """
    
    def __init__(self, redis_host: str = "localhost", redis_port: int = 6379):
        """Initialize the call worker with Redis connection"""
        self.redis_conn = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
        self.queue = Queue('followup_calls', connection=self.redis_conn)
        self.scheduler = Scheduler(connection=self.redis_conn)
        self.call_scheduler = CallScheduler(redis_host=redis_host, redis_port=redis_port)
        self.worker: Optional[Worker] = None
        self.running = False
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.stop()
    
    def start_worker(self, worker_name: Optional[str] = None):
        """
        Start the RQ worker to process call execution jobs
        
        Args:
            worker_name: Optional name for the worker (defaults to hostname-based)
        """
        if self.running:
            logger.warning("Worker is already running")
            return
        
        logger.info("Starting PostOp call execution worker...")
        
        # Create worker instance
        self.worker = Worker(
            [self.queue], 
            connection=self.redis_conn,
            name=worker_name or f"postop-worker-{int(time.time())}"
        )
        
        self.running = True
        
        try:
            # Start processing jobs
            self.worker.work(with_scheduler=True, logging_level=logging.INFO)
        except KeyboardInterrupt:
            logger.info("Worker interrupted by user")
        except Exception as e:
            logger.error(f"Worker error: {e}", exc_info=True)
        finally:
            self.running = False
            logger.info("Worker stopped")
    
    def start_scheduler_daemon(self, check_interval: int = 60):
        """
        Start a daemon process that checks for pending calls and queues them for execution
        
        Args:
            check_interval: How often to check for pending calls (seconds)
        """
        logger.info(f"Starting scheduler daemon with {check_interval}s check interval...")
        
        # Schedule the recurring task to process pending calls
        self.scheduler.schedule(
            scheduled_time=datetime.now(),
            func=process_pending_calls,
            interval=check_interval,
            repeat=None  # Repeat indefinitely
        )
        
        logger.info("Scheduler daemon started - will check for pending calls every {check_interval}s")
    
    def stop(self):
        """Stop the worker gracefully"""
        if self.worker and self.running:
            logger.info("Stopping worker...")
            self.worker.request_stop()
            self.running = False
        else:
            logger.info("Worker not running")
    
    def get_worker_stats(self) -> dict:
        """Get statistics about the worker and queue"""
        stats = {
            "queue_size": len(self.queue),
            "failed_jobs": len(self.queue.failed_job_registry),
            "finished_jobs": len(self.queue.finished_job_registry),
            "started_jobs": len(self.queue.started_job_registry),
            "deferred_jobs": len(self.queue.deferred_job_registry),
            "scheduled_jobs": len(self.queue.scheduled_job_registry),
            "worker_count": len(Worker.all(connection=self.redis_conn)),
            "is_running": self.running
        }
        
        # Get pending calls from scheduler
        pending_calls = self.call_scheduler.get_pending_calls(limit=100)
        stats["pending_calls"] = len(pending_calls)
        
        return stats
    
    def clear_failed_jobs(self):
        """Clear all failed jobs from the queue"""
        count = len(self.queue.failed_job_registry)
        self.queue.failed_job_registry.clear()
        logger.info(f"Cleared {count} failed jobs")
        return count
    
    def retry_failed_jobs(self, max_retries: int = 3):
        """
        Retry failed jobs that haven't exceeded max retries
        
        Args:
            max_retries: Maximum number of retry attempts
        """
        failed_jobs = self.queue.failed_job_registry.get_job_ids()
        retried_count = 0
        
        for job_id in failed_jobs:
            try:
                job = Job.fetch(job_id, connection=self.redis_conn)
                
                # Check if job has retries left
                retry_count = job.meta.get('retry_count', 0)
                if retry_count < max_retries:
                    # Update retry count
                    job.meta['retry_count'] = retry_count + 1
                    job.save_meta()
                    
                    # Requeue the job
                    self.queue.requeue(job_id)
                    retried_count += 1
                    logger.info(f"Retried job {job_id} (attempt {retry_count + 1})")
                else:
                    logger.warning(f"Job {job_id} has exceeded max retries ({max_retries})")
                    
            except Exception as e:
                logger.error(f"Error retrying job {job_id}: {e}")
        
        logger.info(f"Retried {retried_count} failed jobs")
        return retried_count


class CallSchedulerDaemon:
    """
    Standalone daemon for monitoring and scheduling pending calls
    """
    
    def __init__(self, redis_host: str = "localhost", redis_port: int = 6379):
        """Initialize the scheduler daemon"""
        self.call_scheduler = CallScheduler(redis_host=redis_host, redis_port=redis_port)
        self.redis_conn = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
        self.queue = Queue('followup_calls', connection=self.redis_conn)
        self.running = False
        
        # Set up signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info(f"Scheduler daemon received signal {signum}, shutting down...")
        self.running = False
    
    def run(self, check_interval: int = 60):
        """
        Run the scheduler daemon
        
        Args:
            check_interval: How often to check for pending calls (seconds)
        """
        logger.info(f"Starting call scheduler daemon (checking every {check_interval}s)")
        self.running = True
        
        while self.running:
            try:
                # Get pending calls that are due
                pending_calls = self.call_scheduler.get_pending_calls(limit=50)
                
                if pending_calls:
                    logger.info(f"Found {len(pending_calls)} pending calls to process")
                    
                    # Queue each call for execution
                    for call in pending_calls:
                        try:
                            from .tasks import execute_followup_call
                            job = self.queue.enqueue(execute_followup_call, call.id)
                            logger.info(f"Queued call {call.id} for execution (job: {job.id})")
                        except Exception as e:
                            logger.error(f"Failed to queue call {call.id}: {e}")
                            # Mark call as failed
                            from .models import CallStatus
                            self.call_scheduler.update_call_status(
                                call.id,
                                CallStatus.FAILED,
                                f"Failed to queue: {str(e)}"
                            )
                else:
                    logger.debug("No pending calls found")
                
                # Wait before next check
                time.sleep(check_interval)
                
            except KeyboardInterrupt:
                logger.info("Scheduler daemon interrupted")
                break
            except Exception as e:
                logger.error(f"Error in scheduler daemon: {e}", exc_info=True)
                time.sleep(check_interval)  # Wait before retrying
        
        logger.info("Scheduler daemon stopped")


def main():
    """
    Main function for running worker or scheduler daemon
    """
    import argparse
    
    parser = argparse.ArgumentParser(description="PostOp AI Call Scheduling Worker")
    parser.add_argument(
        "mode", 
        choices=["worker", "scheduler", "both"], 
        help="Mode to run: worker (process jobs), scheduler (queue pending calls), or both"
    )
    parser.add_argument(
        "--redis-host", 
        default="localhost", 
        help="Redis host (default: localhost)"
    )
    parser.add_argument(
        "--redis-port", 
        type=int, 
        default=6379, 
        help="Redis port (default: 6379)"
    )
    parser.add_argument(
        "--check-interval", 
        type=int, 
        default=60, 
        help="Scheduler check interval in seconds (default: 60)"
    )
    parser.add_argument(
        "--worker-name", 
        help="Name for the worker process"
    )
    parser.add_argument(
        "--log-level", 
        choices=["DEBUG", "INFO", "WARNING", "ERROR"], 
        default="INFO", 
        help="Logging level"
    )
    
    args = parser.parse_args()
    
    # Set up logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    if args.mode == "worker":
        # Run only the RQ worker
        worker = PostOpCallWorker(redis_host=args.redis_host, redis_port=args.redis_port)
        worker.start_worker(worker_name=args.worker_name)
        
    elif args.mode == "scheduler":
        # Run only the scheduler daemon
        daemon = CallSchedulerDaemon(redis_host=args.redis_host, redis_port=args.redis_port)
        daemon.run(check_interval=args.check_interval)
        
    elif args.mode == "both":
        # Run both worker and scheduler in separate processes
        import multiprocessing
        
        def run_worker():
            worker = PostOpCallWorker(redis_host=args.redis_host, redis_port=args.redis_port)
            worker.start_worker(worker_name=args.worker_name)
        
        def run_scheduler():
            daemon = CallSchedulerDaemon(redis_host=args.redis_host, redis_port=args.redis_port)
            daemon.run(check_interval=args.check_interval)
        
        # Start both processes
        worker_process = multiprocessing.Process(target=run_worker)
        scheduler_process = multiprocessing.Process(target=run_scheduler)
        
        try:
            worker_process.start()
            scheduler_process.start()
            
            # Wait for both to complete
            worker_process.join()
            scheduler_process.join()
            
        except KeyboardInterrupt:
            logger.info("Shutting down both processes...")
            worker_process.terminate()
            scheduler_process.terminate()
            worker_process.join()
            scheduler_process.join()


if __name__ == "__main__":
    main()