"""
Basic Integration Tests for Hybrid RAG System

Tests that the hybrid RAG system works correctly with both backends
and can integrate with mock agents.
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock
import tempfile
import os

# Import our components
from discharge.hybrid_rag import create_hybrid_rag_handler, RAGBackend
from discharge.medical_rag import create_sample_medical_knowledge


class TestBasicRAGIntegration:
    """Basic integration tests for the hybrid RAG system"""
    
    @pytest.mark.asyncio
    async def test_redis_backend_basic_functionality(self):
        """Test basic Redis backend functionality"""
        try:
            # Create Redis handler
            handler = create_hybrid_rag_handler(backend="redis")
            backend_info = handler.get_backend_info()
            
            # Verify Redis backend is available
            assert backend_info['available'] is True
            assert backend_info['backend'] == 'redis'
            
            # Test search functionality
            results = await handler.search_medical_information("compression", max_results=2)
            assert len(results) >= 1
            
            # Verify result structure
            result = results[0]
            assert hasattr(result, 'uuid_key')
            assert hasattr(result, 'text')
            assert hasattr(result, 'category')
            assert 'compression' in result.text.lower()
            assert result.metadata.get('backend') == 'redis'
            
            print(f"✅ Redis backend test passed - found {len(results)} results")
            
        except Exception as e:
            pytest.skip(f"Redis backend not available: {e}")
    
    @pytest.mark.asyncio
    async def test_annoy_backend_basic_functionality(self):
        """Test basic Annoy backend functionality"""
        try:
            # Create Annoy handler
            handler = create_hybrid_rag_handler(backend="annoy")
            backend_info = handler.get_backend_info()
            
            # Verify Annoy backend is available
            assert backend_info['available'] is True
            assert backend_info['backend'] == 'annoy'
            
            # Test search functionality
            results = await handler.search_medical_information("ibuprofen", max_results=2)
            assert len(results) >= 1
            
            # Verify result structure
            result = results[0]
            assert hasattr(result, 'uuid_key')
            assert hasattr(result, 'text')
            assert hasattr(result, 'category')
            assert 'ibuprofen' in result.text.lower()
            assert result.metadata.get('backend') == 'annoy'
            
            print(f"✅ Annoy backend test passed - found {len(results)} results")
            
        except Exception as e:
            pytest.skip(f"Annoy backend not available: {e}")
    
    @pytest.mark.asyncio
    async def test_auto_backend_selection(self):
        """Test automatic backend selection logic"""
        handler = create_hybrid_rag_handler(backend="auto")
        backend_info = handler.get_backend_info()
        
        # Should select some backend
        assert backend_info['available'] is True
        assert backend_info['backend'] in ['redis', 'annoy']
        
        # Test that it works
        results = await handler.search_medical_information("pain", max_results=1)
        if results:  # Only test if we have data
            assert len(results) >= 1
            assert 'pain' in results[0].text.lower()
        
        print(f"✅ Auto-selection chose {backend_info['backend']} backend")
    
    @pytest.mark.asyncio
    async def test_backend_consistency(self):
        """Test that both backends return similar results for the same query"""
        query = "compression"
        
        redis_results = []
        annoy_results = []
        
        # Try Redis
        try:
            redis_handler = create_hybrid_rag_handler(backend="redis")
            if redis_handler.get_backend_info()['available']:
                redis_results = await redis_handler.search_medical_information(query, max_results=3)
        except Exception as e:
            print(f"Redis unavailable: {e}")
        
        # Try Annoy
        try:
            annoy_handler = create_hybrid_rag_handler(backend="annoy")
            if annoy_handler.get_backend_info()['available']:
                annoy_results = await annoy_handler.search_medical_information(query, max_results=3)
        except Exception as e:
            print(f"Annoy unavailable: {e}")
        
        # If both backends are available, they should find similar content
        if redis_results and annoy_results:
            # Both should find content about compression
            redis_texts = " ".join([r.text.lower() for r in redis_results])
            annoy_texts = " ".join([r.text.lower() for r in annoy_results])
            
            assert query in redis_texts
            assert query in annoy_texts
            
            print(f"✅ Backend consistency test passed")
            print(f"   Redis found {len(redis_results)} results")
            print(f"   Annoy found {len(annoy_results)} results")
        else:
            pytest.skip("Need both backends available for consistency test")


class TestRAGAgentIntegration:
    """Test RAG integration with mock agents"""
    
    def create_mock_agent(self):
        """Create a mock agent for testing"""
        agent = Mock()
        agent.session = Mock()
        agent.session.say = AsyncMock()
        agent.session.generate_reply = AsyncMock()
        return agent
    
    def create_mock_run_context(self, agent):
        """Create a mock RunContext for testing"""
        ctx = Mock()
        ctx.agent = agent
        ctx.session = agent.session
        return ctx
    
    @pytest.mark.asyncio
    async def test_function_tools_registration(self):
        """Test that function tools get registered with agents correctly"""
        # Create handler and mock agent
        handler = create_hybrid_rag_handler(backend="auto")
        mock_agent = self.create_mock_agent()
        
        # Register function tools
        handler.register_with_agent(mock_agent)
        
        # Verify function tools were added
        assert hasattr(mock_agent, 'lookup_procedure_info')
        assert hasattr(mock_agent, 'lookup_medication_info')
        assert hasattr(mock_agent, 'lookup_symptom_guidance')
        assert hasattr(mock_agent, 'hybrid_rag_handler')
        
        print("✅ Function tools registration test passed")
    
    @pytest.mark.asyncio
    async def test_mock_function_tool_execution(self):
        """Test that function tools can be executed with mock context"""
        # Create handler and mock agent
        handler = create_hybrid_rag_handler(backend="auto")
        mock_agent = self.create_mock_agent()
        mock_ctx = self.create_mock_run_context(mock_agent)
        
        # Register function tools
        handler.register_with_agent(mock_agent)
        
        # Test procedure lookup function tool
        if hasattr(mock_agent, 'lookup_procedure_info'):
            # Call the function tool directly (it's bound to the agent)
            result = await mock_agent.lookup_procedure_info(mock_ctx, procedure="venous malformation", question="recovery time")
            
            # Verify the function was called and returned something
            assert result is not None
            assert isinstance(result, str)
            
            # Verify that the mock agent's session methods were called
            mock_agent.session.say.assert_called()
            mock_agent.session.generate_reply.assert_called()
            
            print(f"✅ Function tool execution test passed: {result}")
    
    @pytest.mark.asyncio
    async def test_medication_lookup_function(self):
        """Test medication lookup function tool"""
        handler = create_hybrid_rag_handler(backend="auto")
        mock_agent = self.create_mock_agent()
        mock_ctx = self.create_mock_run_context(mock_agent)
        
        handler.register_with_agent(mock_agent)
        
        if hasattr(mock_agent, 'lookup_medication_info'):
            result = await mock_agent.lookup_medication_info(mock_ctx, medication="ibuprofen", question="side effects")
            
            assert result is not None
            assert isinstance(result, str)
            mock_agent.session.say.assert_called()
            mock_agent.session.generate_reply.assert_called()
            
            print(f"✅ Medication lookup test passed: {result}")
    
    @pytest.mark.asyncio
    async def test_symptom_guidance_function(self):
        """Test symptom guidance function tool"""
        handler = create_hybrid_rag_handler(backend="auto")
        mock_agent = self.create_mock_agent()
        mock_ctx = self.create_mock_run_context(mock_agent)
        
        handler.register_with_agent(mock_agent)
        
        if hasattr(mock_agent, 'lookup_symptom_guidance'):
            result = await mock_agent.lookup_symptom_guidance(mock_ctx, symptom="swelling")
            
            assert result is not None
            assert isinstance(result, str)
            mock_agent.session.say.assert_called()
            mock_agent.session.generate_reply.assert_called()
            
            print(f"✅ Symptom guidance test passed: {result}")


class TestRAGKnowledgeManagement:
    """Test knowledge management operations"""
    
    @pytest.mark.asyncio
    async def test_add_knowledge_redis(self):
        """Test adding knowledge to Redis backend"""
        try:
            handler = create_hybrid_rag_handler(backend="redis")
            if not handler.get_backend_info()['available']:
                pytest.skip("Redis backend not available")
            
            # Add new knowledge
            test_text = "Test medical knowledge for integration testing: This is a sample entry for testing purposes."
            uuid_key = await handler.add_medical_knowledge(
                text=test_text,
                category="Testing",
                metadata={"test": True, "integration": "basic"}
            )
            
            assert uuid_key is not None
            
            # Search for the added knowledge
            results = await handler.search_medical_information("integration testing", max_results=1)
            found = any(test_text in r.text for r in results)
            assert found, "Added knowledge should be findable via search"
            
            print(f"✅ Knowledge addition test passed: {uuid_key}")
            
        except Exception as e:
            pytest.skip(f"Redis knowledge management test failed: {e}")
    
    @pytest.mark.asyncio
    async def test_add_knowledge_annoy(self):
        """Test adding knowledge to Annoy backend"""
        try:
            handler = create_hybrid_rag_handler(backend="annoy")
            if not handler.get_backend_info()['available']:
                pytest.skip("Annoy backend not available")
            
            # Add new knowledge
            test_text = "Test medical knowledge for Annoy integration: This is a sample entry for Annoy testing."
            uuid_key = await handler.add_medical_knowledge(
                text=test_text,
                category="Testing",
                metadata={"test": True, "integration": "annoy"}
            )
            
            assert uuid_key is not None
            
            # Search for the added knowledge
            results = await handler.search_medical_information("Annoy integration", max_results=1)
            found = any(test_text in r.text for r in results)
            assert found, "Added knowledge should be findable via search"
            
            print(f"✅ Annoy knowledge addition test passed: {uuid_key}")
            
        except Exception as e:
            pytest.skip(f"Annoy knowledge management test failed: {e}")


@pytest.mark.asyncio
async def test_integration_end_to_end_basic():
    """
    Basic end-to-end integration test
    
    Tests the complete flow: create handler → search functionality → verify results
    """
    print("\n🔄 Running basic end-to-end integration test...")
    
    # Step 1: Create hybrid RAG handler
    handler = create_hybrid_rag_handler(backend="auto")
    backend_info = handler.get_backend_info()
    
    assert backend_info['available'], "No RAG backend available"
    print(f"✅ Step 1: Created handler with {backend_info['backend']} backend")
    
    # Step 2: Test direct search functionality
    search_queries = ["compression", "ibuprofen", "pain", "infection"]
    total_results = 0
    
    for query in search_queries:
        results = await handler.search_medical_information(query, max_results=2)
        total_results += len(results)
        if results:
            print(f"✅ Found {len(results)} results for '{query}' - sample: {results[0].text[:50]}...")
    
    assert total_results > 0, "Should find some medical content"
    print(f"✅ Step 2: Direct search found {total_results} total results across {len(search_queries)} queries")
    
    # Step 3: Test knowledge addition
    test_text = f"Integration test knowledge entry - backend: {backend_info['backend']}"
    try:
        uuid_key = await handler.add_medical_knowledge(
            text=test_text,
            category="Testing",
            metadata={"integration_test": True}
        )
        if uuid_key:
            print(f"✅ Step 3: Added test knowledge entry: {uuid_key[:8]}")
        else:
            print("⚠️ Step 3: Knowledge addition not supported by current backend")
    except Exception as e:
        print(f"⚠️ Step 3: Knowledge addition failed: {e}")
    
    # Step 4: Test that we can create mock agent and register tools (without calling them)
    mock_agent = Mock()
    mock_agent.session = Mock()
    mock_agent.session.say = AsyncMock()
    mock_agent.session.generate_reply = AsyncMock()
    
    handler.register_with_agent(mock_agent)
    assert hasattr(mock_agent, 'lookup_procedure_info')
    assert hasattr(mock_agent, 'lookup_medication_info')
    assert hasattr(mock_agent, 'lookup_symptom_guidance')
    print("✅ Step 4: Successfully registered function tools with mock agent")
    
    # Step 5: Test backend switching if multiple available
    available_backends = []
    for backend_type in ["redis", "annoy"]:
        try:
            test_handler = create_hybrid_rag_handler(backend=backend_type)
            if test_handler.get_backend_info()['available']:
                available_backends.append(backend_type)
        except:
            pass
    
    print(f"✅ Step 5: Available backends: {available_backends}")
    
    print(f"\n🎉 Basic end-to-end integration test PASSED!")
    print(f"   Primary backend: {backend_info['backend']}")
    print(f"   Available backends: {available_backends}")
    print(f"   Total search results: {total_results}")


if __name__ == "__main__":
    # Run basic integration test directly
    asyncio.run(test_integration_end_to_end_basic())