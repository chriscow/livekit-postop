"""
Redis-based Vector RAG System for PostOp AI

This module provides an alternative to the Annoy-based RAG system using Redis
with vector similarity search capabilities. Requires Redis Stack or Redis with
RediSearch module.

Advantages over Annoy:
- Real-time updates (no need to rebuild index)
- Distributed storage
- Built-in persistence
- Atomic operations
- Concurrent access
"""

import json
import logging
import uuid
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

import redis
import numpy as np
from livekit.agents import Agent, RunContext, function_tool

logger = logging.getLogger("redis-vector-rag")


@dataclass
class RedisVectorQueryResult:
    """Result from Redis vector similarity search"""
    uuid_key: str
    text: str
    distance: float
    metadata: Dict[str, Any]


class RedisVectorRAGHandler:
    """
    Redis-based RAG handler with vector similarity search
    
    Uses Redis with RediSearch for vector storage and similarity search.
    Provides real-time updates and distributed access.
    """
    
    def __init__(
        self,
        redis_host: str = None,
        redis_port: int = 6379,
        redis_db: int = 0,
        redis_password: Optional[str] = None,
        index_name: str = "medical_knowledge_idx",
        key_prefix: str = "medical:",
        vector_dimension: int = 1536,
        thinking_messages: Optional[List[str]] = None
    ):
        """
        Initialize Redis vector RAG handler
        
        Args:
            redis_host: Redis server host (defaults to REDIS_HOST env var or 'redis')
            redis_port: Redis server port  
            redis_db: Redis database number
            redis_password: Redis password (if required)
            index_name: Name of the Redis search index
            key_prefix: Prefix for Redis keys
            vector_dimension: Dimension of embedding vectors
            thinking_messages: Messages to display during search
        """
        import os
        
        # Default to environment variable or fallback to 'redis' for Docker
        if redis_host is None:
            redis_host = os.environ.get('REDIS_HOST', 'redis')
        
        self.redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
            decode_responses=False  # We need bytes for vectors
        )
        
        self.index_name = index_name
        self.key_prefix = key_prefix
        self.vector_dimension = vector_dimension
        self.thinking_messages = thinking_messages or [
            "Let me search our medical database...",
            "Looking that up in our knowledge base...",
            "Checking the medical guidelines..."
        ]
        
        # Track seen results to avoid repetition
        self._seen_results = set()
        
        # Test connection and initialize
        try:
            self.redis_client.ping()
            self._initialize_index()
            logger.info("Connected to Redis vector database")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    def _initialize_index(self):
        """Initialize the Redis search index if it doesn't exist"""
        try:
            # Check if index exists
            self.redis_client.execute_command("FT.INFO", self.index_name)
            logger.info(f"Using existing Redis index: {self.index_name}")
        except redis.ResponseError:
            # Index doesn't exist, create it
            try:
                schema = [
                    "$.uuid", "AS", "uuid", "TEXT",
                    "$.text", "AS", "text", "TEXT",
                    "$.category", "AS", "category", "TAG",
                    "$.embedding", "AS", "vector", "VECTOR", "FLAT", "6",
                    "TYPE", "FLOAT32", "DIM", str(self.vector_dimension),
                    "DISTANCE_METRIC", "COSINE"
                ]
                
                self.redis_client.execute_command(
                    "FT.CREATE", self.index_name,
                    "ON", "JSON",
                    "PREFIX", "1", self.key_prefix,
                    "SCHEMA", *schema
                )
                logger.info(f"Created new Redis index: {self.index_name}")
            except Exception as e:
                logger.error(f"Failed to create Redis index: {e}")
                raise
    
    async def add_knowledge_entry(
        self,
        text: str,
        embedding: List[float],
        category: str = "General",
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Add a new knowledge entry to Redis
        
        Args:
            text: The medical knowledge text
            embedding: Vector embedding of the text
            category: Category/classification of the knowledge
            metadata: Additional metadata
            
        Returns:
            UUID of the created entry
        """
        entry_uuid = str(uuid.uuid4())
        key = f"{self.key_prefix}{entry_uuid}"
        
        entry_data = {
            "uuid": entry_uuid,
            "text": text,
            "category": category,
            "embedding": embedding,
            "metadata": metadata or {}
        }
        
        try:
            self.redis_client.json().set(key, "$", entry_data)
            logger.info(f"Added knowledge entry: {entry_uuid}")
            return entry_uuid
        except Exception as e:
            logger.error(f"Failed to add knowledge entry: {e}")
            raise
    
    async def update_knowledge_entry(
        self,
        entry_uuid: str,
        text: Optional[str] = None,
        embedding: Optional[List[float]] = None,
        category: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update an existing knowledge entry
        
        Args:
            entry_uuid: UUID of the entry to update
            text: New text (if updating)
            embedding: New embedding (if updating)
            category: New category (if updating)
            metadata: New metadata (if updating)
            
        Returns:
            True if successful, False if entry not found
        """
        key = f"{self.key_prefix}{entry_uuid}"
        
        try:
            # Check if entry exists
            existing = self.redis_client.json().get(key)
            if not existing:
                return False
            
            # Update fields
            updates = {}
            if text is not None:
                updates["$.text"] = text
            if embedding is not None:
                updates["$.embedding"] = embedding
            if category is not None:
                updates["$.category"] = category
            if metadata is not None:
                updates["$.metadata"] = metadata
            
            for path, value in updates.items():
                self.redis_client.json().set(key, path, value)
            
            logger.info(f"Updated knowledge entry: {entry_uuid}")
            return True
        except Exception as e:
            logger.error(f"Failed to update knowledge entry {entry_uuid}: {e}")
            return False
    
    async def delete_knowledge_entry(self, entry_uuid: str) -> bool:
        """
        Delete a knowledge entry
        
        Args:
            entry_uuid: UUID of the entry to delete
            
        Returns:
            True if successful, False if entry not found
        """
        key = f"{self.key_prefix}{entry_uuid}"
        
        try:
            result = self.redis_client.delete(key)
            if result > 0:
                logger.info(f"Deleted knowledge entry: {entry_uuid}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete knowledge entry {entry_uuid}: {e}")
            return False
    
    async def vector_search(
        self,
        query_embedding: List[float],
        limit: int = 5,
        category_filter: Optional[str] = None
    ) -> List[RedisVectorQueryResult]:
        """
        Perform vector similarity search
        
        Args:
            query_embedding: Query vector
            limit: Maximum number of results
            category_filter: Filter by category (optional)
            
        Returns:
            List of search results
        """
        try:
            # Build search query
            query_vector = np.array(query_embedding, dtype=np.float32).tobytes()
            
            if category_filter:
                search_query = f"(@category:{category_filter})=>[KNN {limit} @vector $query_vector]"
            else:
                search_query = f"*=>[KNN {limit} @vector $query_vector]"
            
            # Execute search
            search_params = {
                "query_vector": query_vector
            }
            
            results = self.redis_client.execute_command(
                "FT.SEARCH", self.index_name, search_query,
                "PARAMS", "2", "query_vector", query_vector,
                "RETURN", "3", "$.uuid", "$.text", "$.metadata",
                "SORTBY", "__vector_score",
                "LIMIT", "0", str(limit),
                "DIALECT", "2"
            )
            
            # Parse results
            parsed_results = []
            if len(results) > 1:  # First element is count
                for i in range(1, len(results), 2):  # Results come in pairs
                    if i + 1 < len(results):
                        key = results[i].decode('utf-8')
                        fields = results[i + 1]
                        
                        # Extract data from fields
                        uuid_key = None
                        text = None
                        metadata = {}
                        distance = 0.0
                        
                        for j in range(0, len(fields), 2):
                            if j + 1 < len(fields):
                                field_name = fields[j].decode('utf-8')
                                field_value = fields[j + 1].decode('utf-8')
                                
                                if field_name == "$.uuid":
                                    uuid_key = field_value
                                elif field_name == "$.text":
                                    text = field_value
                                elif field_name == "$.metadata":
                                    try:
                                        metadata = json.loads(field_value)
                                    except json.JSONDecodeError:
                                        metadata = {}
                                elif field_name == "__vector_score":
                                    distance = float(field_value)
                        
                        if uuid_key and text:
                            parsed_results.append(RedisVectorQueryResult(
                                uuid_key=uuid_key,
                                text=text,
                                distance=distance,
                                metadata=metadata
                            ))
            
            return parsed_results
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []
    
    async def text_search(
        self,
        query: str,
        limit: int = 5,
        category_filter: Optional[str] = None
    ) -> List[RedisVectorQueryResult]:
        """
        Perform text-based search
        
        Args:
            query: Text query
            limit: Maximum number of results
            category_filter: Filter by category (optional)
            
        Returns:
            List of search results
        """
        try:
            # For now, use a simple approach - get all entries and filter manually
            # This is more reliable than dealing with RediSearch query syntax issues
            all_entries = await self.get_all_entries(category_filter)
            
            query_lower = query.lower()
            matching_entries = []
            
            for entry in all_entries:
                if query_lower in entry.text.lower():
                    matching_entries.append(entry)
                    if len(matching_entries) >= limit:
                        break
            
            return matching_entries
            
        except Exception as e:
            logger.error(f"Text search failed: {e}")
            return []
    
    async def get_all_entries(self, category_filter: Optional[str] = None) -> List[RedisVectorQueryResult]:
        """
        Get all knowledge entries
        
        Args:
            category_filter: Filter by category (optional)
            
        Returns:
            List of all entries
        """
        try:
            if category_filter:
                search_query = f"@category:{category_filter}"
            else:
                search_query = "*"
            
            # Use a simpler approach - get all keys and fetch data directly
            pattern = f"{self.key_prefix}*"
            keys = self.redis_client.keys(pattern)
            
            parsed_results = []
            for key in keys:
                try:
                    key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                    data = self.redis_client.json().get(key_str)
                    
                    if data and isinstance(data, dict):
                        uuid_key = data.get('uuid')
                        text = data.get('text')
                        category = data.get('category', 'Unknown')
                        metadata = data.get('metadata', {})
                        
                        # Apply category filter if specified
                        if category_filter and category.lower() != category_filter.lower():
                            continue
                        
                        if uuid_key and text:
                            # Add category to metadata for display
                            metadata['category'] = category
                            parsed_results.append(RedisVectorQueryResult(
                                uuid_key=uuid_key,
                                text=text,
                                distance=0.0,
                                metadata=metadata
                            ))
                except Exception as e:
                    logger.warning(f"Failed to parse entry {key}: {e}")
                    continue
            
            return parsed_results
            
        except Exception as e:
            logger.error(f"Failed to get all entries: {e}")
            return []
    
    async def get_entry_count(self) -> int:
        """Get total number of knowledge entries"""
        try:
            results = self.redis_client.execute_command(
                "FT.SEARCH", self.index_name, "*",
                "LIMIT", "0", "0",  # Don't return any documents, just count
                "DIALECT", "2"
            )
            return int(results[0]) if results else 0
        except Exception as e:
            logger.error(f"Failed to get entry count: {e}")
            return 0
    
    def register_with_agent(self, agent: Agent) -> None:
        """
        Register medical lookup function tools with an agent
        
        Args:
            agent: The agent to enhance with Redis RAG capabilities
        """
        
        @function_tool
        async def lookup_procedure_info(ctx: RunContext, procedure: str, question: str = ""):
            """Look up information about a specific medical procedure"""
            await ctx.session.say(f"Let me search for information about {procedure}...")
            
            # Search by category first, then by text
            results = await self.vector_search(
                query_embedding=[],  # Would need embeddings in real implementation
                limit=2,
                category_filter="Procedure-Specific"
            )
            
            if not results:
                results = await self.text_search(procedure, limit=2)
            
            if results:
                context = "\n\n".join([r.text for r in results])
                await ctx.session.generate_reply(
                    instructions=f"""
                    The patient is asking about the procedure: {procedure}.
                    {f"Specific question: {question}" if question else ""}
                    
                    Relevant medical information:
                    {context}
                    
                    Provide a clear, helpful response based on this information.
                    """
                )
                return f"Provided information about {procedure}"
            else:
                await ctx.session.generate_reply(
                    instructions=f"I don't have specific information about {procedure} in my database. I recommend contacting your healthcare provider."
                )
                return "No specific procedure information found"
        
        # Add the function tools to the agent
        agent.lookup_procedure_info = lookup_procedure_info.__get__(agent)
        agent.redis_rag_handler = self
        
        logger.info("Registered Redis RAG function tools with agent")


async def migrate_annoy_to_redis(
    annoy_knowledge_path: str,
    redis_handler: RedisVectorRAGHandler,
    embeddings_generator=None
) -> int:
    """
    Migrate knowledge from Annoy-based system to Redis
    
    Args:
        annoy_knowledge_path: Path to existing knowledge.pkl file
        redis_handler: Initialized Redis RAG handler
        embeddings_generator: Function to generate embeddings for text
        
    Returns:
        Number of entries migrated
    """
    import pickle
    
    try:
        # Load existing knowledge
        with open(annoy_knowledge_path, "rb") as f:
            knowledge_dict = pickle.load(f)
        
        migrated_count = 0
        for uuid_key, text in knowledge_dict.items():
            # Generate embeddings if generator provided
            embedding = []
            if embeddings_generator:
                embedding = await embeddings_generator(text)
            
            # Categorize text
            category = _categorize_text(text)
            
            # Add to Redis
            await redis_handler.add_knowledge_entry(
                text=text,
                embedding=embedding,
                category=category,
                metadata={"migrated_from_annoy": True, "original_uuid": uuid_key}
            )
            migrated_count += 1
        
        logger.info(f"Migrated {migrated_count} entries from Annoy to Redis")
        return migrated_count
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return 0


def _categorize_text(text: str) -> str:
    """Categorize medical text based on keywords"""
    text_lower = text.lower()
    if 'venous malformation' in text_lower or 'bleomycin' in text_lower:
        return 'Procedure-Specific'
    elif 'pain' in text_lower or 'medication' in text_lower or 'ibuprofen' in text_lower:
        return 'Pain Management'
    elif 'infection' in text_lower or 'fever' in text_lower or 'antibiotic' in text_lower:
        return 'Infection Care'
    elif 'child' in text_lower or 'pediatric' in text_lower or 'school' in text_lower:
        return 'Pediatric'
    elif 'compression' in text_lower or 'bandage' in text_lower:
        return 'Wound Care'
    elif 'activity' in text_lower or 'exercise' in text_lower or 'recovery' in text_lower:
        return 'Recovery'
    elif 'emergency' in text_lower or 'call' in text_lower or 'contact' in text_lower:
        return 'Emergency'
    else:
        return 'General'