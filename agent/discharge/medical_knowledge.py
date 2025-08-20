"""
Redis-based Medical Knowledge System for PostOp AI

This module provides a simple Redis-based medical knowledge storage and retrieval
system for the PostOp AI agent. It uses Redis hash structures for storage and
simple text matching for search.
"""

import logging
import redis
import uuid
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from livekit.agents import Agent, RunContext, function_tool

logger = logging.getLogger("medical-knowledge")


@dataclass
class MedicalKnowledgeEntry:
    """Represents a medical knowledge entry"""
    id: str
    text: str
    category: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    relevance_score: float = 0.0


class MedicalKnowledgeHandler:
    """
    Redis-based medical knowledge handler for PostOp AI
    
    Stores medical knowledge in Redis hashes and provides simple text-based
    search functionality for agent function tools.
    """
    
    def __init__(self, redis_url: str = "redis://redis:6379/0"):
        """
        Initialize medical knowledge handler
        
        Args:
            redis_url: Redis connection URL
        """
        self.redis_client = redis.from_url(redis_url)
        self.knowledge_prefix = "medical_knowledge:"
        
        self.thinking_messages = [
            "Let me search our medical database...",
            "Looking that up in our knowledge base...",
            "Checking the medical guidelines..."
        ]
        
        # Test Redis connection
        try:
            self.redis_client.ping()
            logger.info("Medical knowledge handler connected to Redis")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    async def search_knowledge(self, query: str, max_results: int = 5) -> List[MedicalKnowledgeEntry]:
        """
        Search medical knowledge using simple text matching
        
        Args:
            query: Search query
            max_results: Maximum number of results to return
            
        Returns:
            List of matching medical knowledge entries
        """
        try:
            # Get all medical knowledge keys
            keys = self.redis_client.keys(f"{self.knowledge_prefix}*")
            results = []
            query_lower = query.lower()
            
            for key in keys:
                # Get the knowledge entry
                entry_data = self.redis_client.hgetall(key)
                if not entry_data:
                    continue
                
                # Convert bytes to strings
                text = entry_data.get(b'text', b'').decode('utf-8')
                category = entry_data.get(b'category', b'general').decode('utf-8')
                entry_id = entry_data.get(b'id', key.decode().split(':')[-1]).decode('utf-8')
                
                # Simple text matching
                if query_lower in text.lower():
                    # Calculate simple relevance score based on query occurrence
                    relevance = text.lower().count(query_lower) / len(text.split())
                    
                    results.append(MedicalKnowledgeEntry(
                        id=entry_id,
                        text=text,
                        category=category,
                        relevance_score=relevance,
                        metadata={"source": "redis"}
                    ))
            
            # Sort by relevance and return top results
            results.sort(key=lambda x: x.relevance_score, reverse=True)
            return results[:max_results]
            
        except Exception as e:
            logger.error(f"Knowledge search failed: {e}")
            return []
    
    async def add_knowledge(self, text: str, category: str, knowledge_id: str = None) -> str:
        """
        Add medical knowledge entry
        
        Args:
            text: Knowledge text content
            category: Knowledge category
            knowledge_id: Optional specific ID (will generate UUID if not provided)
            
        Returns:
            ID of the created knowledge entry
        """
        try:
            if not knowledge_id:
                knowledge_id = str(uuid.uuid4())
            
            key = f"{self.knowledge_prefix}{knowledge_id}"
            
            # Store as Redis hash
            self.redis_client.hset(key, mapping={
                'id': knowledge_id,
                'text': text,
                'category': category
            })
            
            logger.info(f"Added medical knowledge: {knowledge_id} ({category})")
            return knowledge_id
            
        except Exception as e:
            logger.error(f"Failed to add knowledge: {e}")
            raise
    
    async def get_knowledge_count(self) -> int:
        """Get total number of knowledge entries"""
        try:
            keys = self.redis_client.keys(f"{self.knowledge_prefix}*")
            return len(keys)
        except Exception as e:
            logger.error(f"Failed to get knowledge count: {e}")
            return 0
    
    async def delete_knowledge(self, knowledge_id: str) -> bool:
        """Delete a knowledge entry"""
        try:
            key = f"{self.knowledge_prefix}{knowledge_id}"
            result = self.redis_client.delete(key)
            return result > 0
        except Exception as e:
            logger.error(f"Failed to delete knowledge {knowledge_id}: {e}")
            return False
    
    def register_with_agent(self, agent: Agent) -> None:
        """
        Register medical lookup function tools with an agent
        
        Args:
            agent: The agent to enhance with medical knowledge capabilities
        """
        
        @function_tool
        async def lookup_procedure_info(ctx: RunContext, procedure: str, question: str = ""):
            """Look up information about a specific medical procedure"""
            import random
            
            await ctx.session.say(random.choice(self.thinking_messages))
            
            search_query = f"procedure {procedure} {question}".strip()
            results = await self.search_knowledge(search_query, max_results=2)
            
            if results:
                context = "\n\n".join([r.text for r in results])
                
                await ctx.session.generate_reply(
                    instructions=f"""
                    The patient is asking about the procedure: {procedure}.
                    {f"Specific question: {question}" if question else ""}
                    
                    Relevant medical information:
                    {context}
                    
                    Provide a clear, helpful response based on this information.
                    Be caring and reassuring while being medically accurate.
                    """
                )
                return f"Provided information about {procedure}"
            else:
                await ctx.session.generate_reply(
                    instructions=f"I don't have specific information about {procedure} in my database. I recommend contacting your healthcare provider for detailed information."
                )
                return "No specific procedure information found"
        
        @function_tool
        async def lookup_medication_info(ctx: RunContext, medication: str, question: str = ""):
            """Look up information about medications"""
            import random
            
            await ctx.session.say(random.choice(self.thinking_messages))
            
            search_query = f"medication {medication} {question}".strip()
            results = await self.search_knowledge(search_query, max_results=2)
            
            if results:
                context = "\n\n".join([r.text for r in results])
                
                await ctx.session.generate_reply(
                    instructions=f"""
                    The patient is asking about the medication: {medication}.
                    {f"Specific question: {question}" if question else ""}
                    
                    Relevant medical information:
                    {context}
                    
                    Provide helpful information about this medication. Always remind them to follow their doctor's specific instructions.
                    """
                )
                return f"Provided information about {medication}"
            else:
                await ctx.session.generate_reply(
                    instructions=f"I don't have specific information about {medication} in my database. Please follow the instructions on your medication bottle and contact your healthcare provider with any questions."
                )
                return "No specific medication information found"
        
        @function_tool  
        async def lookup_symptom_guidance(ctx: RunContext, symptom: str):
            """Look up guidance about post-operative symptoms"""
            import random
            
            await ctx.session.say(random.choice(self.thinking_messages))
            
            search_query = f"symptom {symptom} post-operative recovery"
            results = await self.search_knowledge(search_query, max_results=2)
            
            if results:
                context = "\n\n".join([r.text for r in results])
                
                await ctx.session.generate_reply(
                    instructions=f"""
                    The patient is experiencing: {symptom}
                    
                    Relevant medical guidance:
                    {context}
                    
                    Provide helpful guidance about this symptom. Always emphasize when they should contact their healthcare provider.
                    """
                )
                return f"Provided guidance about {symptom}"
            else:
                await ctx.session.generate_reply(
                    instructions=f"I don't have specific guidance about {symptom} in my database. If you're concerned about this symptom, please contact your healthcare provider promptly."
                )
                return "No specific symptom guidance found"
        
        @function_tool
        async def lookup_wound_care(ctx: RunContext, wound_type: str = "", question: str = ""):
            """Look up wound care information"""
            import random
            
            await ctx.session.say(random.choice(self.thinking_messages))
            
            search_query = f"wound care {wound_type} {question}".strip()
            results = await self.search_knowledge(search_query, max_results=2)
            
            if results:
                context = "\n\n".join([r.text for r in results])
                
                await ctx.session.generate_reply(
                    instructions=f"""
                    The patient is asking about wound care.
                    {f"Wound type: {wound_type}" if wound_type else ""}
                    {f"Specific question: {question}" if question else ""}
                    
                    Relevant wound care information:
                    {context}
                    
                    Provide clear, practical wound care guidance based on this information.
                    """
                )
                return f"Provided wound care information"
            else:
                await ctx.session.generate_reply(
                    instructions="I don't have specific wound care information in my database. Please follow the care instructions provided by your healthcare provider and contact them with any concerns."
                )
                return "No specific wound care information found"
        
        # Add the function tools to the agent
        agent.lookup_procedure_info = lookup_procedure_info.__get__(agent)
        agent.lookup_medication_info = lookup_medication_info.__get__(agent)
        agent.lookup_symptom_guidance = lookup_symptom_guidance.__get__(agent)
        agent.lookup_wound_care = lookup_wound_care.__get__(agent)
        
        # Store reference to knowledge handler
        agent.medical_knowledge_handler = self
        
        logger.info("Registered medical knowledge function tools with agent")


# Convenience function for easy integration
def create_medical_knowledge_handler(redis_url: str = "redis://redis:6379/0") -> MedicalKnowledgeHandler:
    """
    Create a medical knowledge handler with Redis backend
    
    Args:
        redis_url: Redis connection URL
        
    Returns:
        Configured MedicalKnowledgeHandler instance
    """
    return MedicalKnowledgeHandler(redis_url=redis_url)