"""
Tests for worker functionality
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from scheduling.worker import PostOpCallWorker, CallSchedulerDaemon
from scheduling.models import CallScheduleItem, CallStatus, CallType


class TestPostOpCallWorker:
    """Tests for PostOpCallWorker class"""
    
    @patch('scheduling.worker.redis.Redis')
    @patch('scheduling.worker.Queue')
    @patch('scheduling.worker.Scheduler')
    def test_init(self, mock_scheduler, mock_queue, mock_redis):
        """Test worker initialization"""
        worker = PostOpCallWorker(redis_host="test-host", redis_port=1234)
        
        # Verify Redis connection
        mock_redis.assert_called_once_with(host="test-host", port=1234, decode_responses=True)
        
        # Verify queue and scheduler setup
        mock_queue.assert_called_once()
        mock_scheduler.assert_called_once()
        
        assert worker.running is False
        assert worker.worker is None
    
    @patch('scheduling.worker.redis.Redis')
    @patch('scheduling.worker.Worker')
    def test_start_worker(self, mock_worker_class, mock_redis):
        """Test starting the RQ worker"""
        mock_worker_instance = Mock()
        mock_worker_class.return_value = mock_worker_instance
        
        worker = PostOpCallWorker()
        worker.start_worker("test-worker")
        
        # Verify worker was created and started
        mock_worker_class.assert_called_once()
        mock_worker_instance.work.assert_called_once_with(
            with_scheduler=True, 
            logging_level=20  # INFO level
        )
        
        assert worker.running is True
    
    @patch('scheduling.worker.redis.Redis')
    def test_get_worker_stats(self, mock_redis):
        """Test getting worker statistics"""
        # Mock Redis client and queue registries
        mock_redis_instance = Mock()
        mock_redis.return_value = mock_redis_instance
        
        worker = PostOpCallWorker()
        
        # Mock queue registries
        worker.queue = Mock()
        worker.queue.__len__ = Mock(return_value=5)
        worker.queue.failed_job_registry = Mock(__len__=Mock(return_value=2))
        worker.queue.finished_job_registry = Mock(__len__=Mock(return_value=10))
        worker.queue.started_job_registry = Mock(__len__=Mock(return_value=1))
        worker.queue.deferred_job_registry = Mock(__len__=Mock(return_value=0))
        worker.queue.scheduled_job_registry = Mock(__len__=Mock(return_value=3))
        
        # Mock call scheduler
        mock_pending_calls = [Mock() for _ in range(7)]
        worker.call_scheduler = Mock()
        worker.call_scheduler.get_pending_calls.return_value = mock_pending_calls
        
        # Mock Worker.all()
        with patch('scheduling.worker.Worker.all', return_value=[Mock(), Mock()]):
            stats = worker.get_worker_stats()
        
        assert stats['queue_size'] == 5
        assert stats['failed_jobs'] == 2
        assert stats['finished_jobs'] == 10
        assert stats['started_jobs'] == 1
        assert stats['deferred_jobs'] == 0
        assert stats['scheduled_jobs'] == 3
        assert stats['worker_count'] == 2
        assert stats['pending_calls'] == 7
        assert stats['is_running'] is False
    
    @patch('scheduling.worker.redis.Redis')
    def test_clear_failed_jobs(self, mock_redis):
        """Test clearing failed jobs"""
        worker = PostOpCallWorker()
        worker.queue = Mock()
        worker.queue.failed_job_registry = Mock()
        worker.queue.failed_job_registry.__len__ = Mock(return_value=5)
        
        count = worker.clear_failed_jobs()
        
        assert count == 5
        worker.queue.failed_job_registry.clear.assert_called_once()
    
    @patch('scheduling.worker.redis.Redis')
    @patch('scheduling.worker.Job')
    def test_retry_failed_jobs(self, mock_job_class, mock_redis):
        """Test retrying failed jobs"""
        worker = PostOpCallWorker()
        worker.queue = Mock()
        
        # Mock failed job IDs
        worker.queue.failed_job_registry.get_job_ids.return_value = ['job1', 'job2', 'job3']
        
        # Mock jobs with different retry counts
        job1 = Mock()
        job1.meta = {'retry_count': 1}
        job2 = Mock()
        job2.meta = {'retry_count': 3}  # Max retries exceeded
        job3 = Mock()
        job3.meta = {}  # No retry count yet
        
        def mock_fetch(job_id, connection):
            if job_id == 'job1':
                return job1
            elif job_id == 'job2':
                return job2
            elif job_id == 'job3':
                return job3
        
        mock_job_class.fetch = mock_fetch
        
        count = worker.retry_failed_jobs(max_retries=3)
        
        # Should retry job1 and job3, but not job2
        assert count == 2
        worker.queue.requeue.assert_any_call('job1')
        worker.queue.requeue.assert_any_call('job3')
        assert worker.queue.requeue.call_count == 2


class TestCallSchedulerDaemon:
    """Tests for CallSchedulerDaemon class"""
    
    @patch('scheduling.worker.redis.Redis')
    @patch('scheduling.worker.Queue')
    def test_init(self, mock_queue, mock_redis):
        """Test daemon initialization"""
        daemon = CallSchedulerDaemon(redis_host="test-host", redis_port=1234)
        
        mock_redis.assert_called_once_with(host="test-host", port=1234, decode_responses=True)
        mock_queue.assert_called_once_with('followup_calls', connection=mock_redis.return_value)
        
        assert daemon.running is False
    
    @patch('scheduling.worker.redis.Redis')
    @patch('scheduling.worker.Queue')
    @patch('scheduling.worker.time.sleep')
    def test_run_with_pending_calls(self, mock_sleep, mock_queue, mock_redis):
        """Test daemon run with pending calls"""
        daemon = CallSchedulerDaemon()
        
        # Mock pending calls
        mock_call1 = CallScheduleItem(
            id="call1",
            patient_id="patient1",
            patient_phone="+1234567890",
            scheduled_time=datetime.now(),
            call_type=CallType.WELLNESS_CHECK,
            priority=1,
            llm_prompt="Test call 1"
        )
        mock_call2 = CallScheduleItem(
            id="call2",
            patient_id="patient2", 
            patient_phone="+0987654321",
            scheduled_time=datetime.now(),
            call_type=CallType.DISCHARGE_REMINDER,
            priority=2,
            llm_prompt="Test call 2"
        )
        
        daemon.call_scheduler = Mock()
        daemon.call_scheduler.get_pending_calls.side_effect = [
            [mock_call1, mock_call2],  # First iteration
            []  # Second iteration - no more calls
        ]
        
        # Mock queue
        mock_job = Mock()
        mock_job.id = "job-123"
        daemon.queue = Mock()
        daemon.queue.enqueue.return_value = mock_job
        
        # Mock sleep to control loop
        def side_effect(seconds):
            if mock_sleep.call_count >= 2:
                daemon.running = False  # Stop after second iteration
        
        mock_sleep.side_effect = side_effect
        
        daemon.run(check_interval=1)
        
        # Verify calls were queued
        assert daemon.queue.enqueue.call_count == 2
        daemon.queue.enqueue.assert_any_call(daemon.queue.enqueue.call_args_list[0][0][0], "call1")
        daemon.queue.enqueue.assert_any_call(daemon.queue.enqueue.call_args_list[1][0][0], "call2")
    
    @patch('scheduling.worker.redis.Redis')
    @patch('scheduling.worker.Queue')
    @patch('scheduling.worker.time.sleep')
    def test_run_with_queue_failure(self, mock_sleep, mock_queue, mock_redis):
        """Test daemon handling queue failures"""
        daemon = CallSchedulerDaemon()
        
        # Mock pending call
        mock_call = CallScheduleItem(
            id="call1",
            patient_id="patient1",
            patient_phone="+1234567890",
            scheduled_time=datetime.now(),
            call_type=CallType.WELLNESS_CHECK,
            priority=1,
            llm_prompt="Test call"
        )
        
        daemon.call_scheduler = Mock()
        daemon.call_scheduler.get_pending_calls.side_effect = [
            [mock_call],  # First iteration
            []  # Second iteration
        ]
        
        # Mock queue to fail
        daemon.queue = Mock()
        daemon.queue.enqueue.side_effect = Exception("Queue failure")
        
        # Mock sleep to control loop
        def side_effect(seconds):
            if mock_sleep.call_count >= 2:
                daemon.running = False
        
        mock_sleep.side_effect = side_effect
        
        daemon.run(check_interval=1)
        
        # Verify call status was updated to failed
        daemon.call_scheduler.update_call_status.assert_called_once_with(
            "call1",
            CallStatus.FAILED,
            "Failed to queue: Queue failure"
        )
    
    @patch('scheduling.worker.redis.Redis')
    def test_signal_handler(self, mock_redis):
        """Test signal handler stops daemon gracefully"""
        daemon = CallSchedulerDaemon()
        daemon.running = True
        
        # Simulate signal
        daemon._signal_handler(2, None)  # SIGINT
        
        assert daemon.running is False


class TestWorkerIntegration:
    """Integration tests for worker components"""
    
    @patch('scheduling.worker.multiprocessing.Process')
    def test_main_both_mode(self, mock_process):
        """Test main function in 'both' mode"""
        from scheduling.worker import main
        
        # Mock process instances
        mock_worker_process = Mock()
        mock_scheduler_process = Mock()
        mock_process.side_effect = [mock_worker_process, mock_scheduler_process]
        
        # Mock sys.argv
        test_args = ['worker.py', 'both', '--redis-host', 'localhost']
        
        with patch('sys.argv', test_args):
            with patch('scheduling.worker.logging.basicConfig'):
                # Mock KeyboardInterrupt to exit gracefully
                mock_worker_process.join.side_effect = KeyboardInterrupt()
                
                try:
                    main()
                except SystemExit:
                    pass  # Expected for argparse
                except KeyboardInterrupt:
                    pass  # Expected from our mock
        
        # Verify both processes were started
        mock_worker_process.start.assert_called_once()
        mock_scheduler_process.start.assert_called_once()