"""
Tests for medical RAG functionality
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path

from discharge.medical_rag import (
    MedicalRAGHandler, ThinkingStyle, create_sample_medical_knowledge,
    MedicalAnnoyIndex, MedicalQueryResult
)


class TestMedicalRAGHandler:
    """Tests for MedicalRAGHandler class"""
    
    def test_init_with_missing_database(self):
        """Test initialization when database files don't exist"""
        handler = MedicalRAGHandler(
            index_path="/nonexistent/path",
            data_path="/nonexistent/file.pkl"
        )
        
        assert handler._annoy_index is None
        assert handler._medical_knowledge == {}
    
    @patch('discharge.medical_rag.MedicalAnnoyIndex.load')
    @patch('builtins.open')
    @patch('pickle.load')
    @patch('pathlib.Path.exists')
    def test_init_with_existing_database(self, mock_exists, mock_pickle, mock_open, mock_load):
        """Test initialization with existing database"""
        # Mock file existence
        mock_exists.return_value = True
        
        # Mock loaded data
        mock_index = Mock()
        mock_index.size = 10
        mock_load.return_value = mock_index
        
        mock_knowledge = {"key1": "value1", "key2": "value2"}
        mock_pickle.return_value = mock_knowledge
        
        handler = MedicalRAGHandler(
            index_path="/mock/path",
            data_path="/mock/file.pkl"
        )
        
        assert handler._annoy_index == mock_index
        assert handler._medical_knowledge == mock_knowledge
    
    @pytest.mark.asyncio
    async def test_handle_thinking_none(self):
        """Test thinking handling with NONE style"""
        handler = MedicalRAGHandler(
            index_path="/mock",
            data_path="/mock",
            thinking_style=ThinkingStyle.NONE
        )
        
        mock_agent = Mock()
        await handler._handle_thinking(mock_agent)
        
        # Should not call agent.session.say
        mock_agent.session.say.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_handle_thinking_message(self):
        """Test thinking handling with MESSAGE style"""
        custom_messages = ["Looking that up...", "Checking database..."]
        handler = MedicalRAGHandler(
            index_path="/mock",
            data_path="/mock",
            thinking_style=ThinkingStyle.MESSAGE,
            thinking_messages=custom_messages
        )
        
        mock_agent = Mock()
        mock_agent.session.say = AsyncMock()
        
        await handler._handle_thinking(mock_agent)
        
        # Should call say with one of the custom messages
        mock_agent.session.say.assert_called_once()
        called_message = mock_agent.session.say.call_args[0][0]
        assert called_message in custom_messages
    
    @pytest.mark.asyncio
    async def test_handle_thinking_llm(self):
        """Test thinking handling with LLM style"""
        handler = MedicalRAGHandler(
            index_path="/mock",
            data_path="/mock",
            thinking_style=ThinkingStyle.LLM,
            thinking_prompt="Generate thinking message"
        )
        
        mock_agent = Mock()
        mock_agent.session.say = AsyncMock()
        mock_agent._llm.complete = AsyncMock()
        
        # Mock LLM response
        mock_response = Mock()
        mock_response.text = "Let me check that for you..."
        mock_agent._llm.complete.return_value = mock_response
        
        await handler._handle_thinking(mock_agent)
        
        # Should call LLM and say the response
        mock_agent._llm.complete.assert_called_once_with("Generate thinking message")
        mock_agent.session.say.assert_called_once_with("Let me check that for you...")
    
    @pytest.mark.asyncio
    @patch('discharge.medical_rag.openai.create_embeddings')
    async def test_lookup_medical_information_no_index(self, mock_embeddings):
        """Test lookup when no index is available"""
        handler = MedicalRAGHandler(index_path="/mock", data_path="/mock")
        handler._annoy_index = None
        
        result = await handler.lookup_medical_information("test query")
        
        assert result == ""
        mock_embeddings.assert_not_called()
    
    @pytest.mark.asyncio
    @patch('discharge.medical_rag.openai.create_embeddings')
    async def test_lookup_medical_information_success(self, mock_embeddings):
        """Test successful medical information lookup"""
        # Setup handler with mock index
        handler = MedicalRAGHandler(index_path="/mock", data_path="/mock")
        
        # Mock index
        mock_index = Mock()
        mock_query_result1 = MedicalQueryResult(
            userdata="uuid1",
            distance=0.1
        )
        mock_query_result2 = MedicalQueryResult(
            userdata="uuid2", 
            distance=0.2
        )
        mock_index.query.return_value = [mock_query_result1, mock_query_result2]
        handler._annoy_index = mock_index
        
        # Mock knowledge
        handler._medical_knowledge = {
            "uuid1": "This is medical information about procedure A",
            "uuid2": "This is information about medication B"
        }
        
        # Mock embeddings
        mock_embedding = Mock()
        mock_embedding.embedding = [0.1, 0.2, 0.3]
        mock_embeddings.return_value = [mock_embedding]
        
        result = await handler.lookup_medical_information("procedure A information")
        
        # Verify embeddings were created
        mock_embeddings.assert_called_once_with(
            input=["procedure A information"],
            model="text-embedding-3-small",
            dimensions=1536
        )
        
        # Verify index was queried
        mock_index.query.assert_called_once_with([0.1, 0.2, 0.3], n=4)  # max_results * 2
        
        # Verify result contains both pieces of information
        assert "procedure A" in result
        assert "medication B" in result
        assert "uuid1" in handler._seen_results
        assert "uuid2" in handler._seen_results
    
    @pytest.mark.asyncio
    @patch('discharge.medical_rag.openai.create_embeddings')
    def test_lookup_medical_information_filters_seen(self, mock_embeddings):
        """Test that lookup filters out previously seen results"""
        handler = MedicalRAGHandler(index_path="/mock", data_path="/mock")
        
        # Pre-populate seen results
        handler._seen_results.add("uuid1")
        
        # Mock index
        mock_index = Mock()
        mock_query_result1 = MedicalQueryResult(userdata="uuid1", distance=0.1)  # Already seen
        mock_query_result2 = MedicalQueryResult(userdata="uuid2", distance=0.2)  # New
        mock_index.query.return_value = [mock_query_result1, mock_query_result2]
        handler._annoy_index = mock_index
        
        # Mock knowledge
        handler._medical_knowledge = {
            "uuid1": "Already seen information",
            "uuid2": "New medical information"
        }
        
        # Mock embeddings
        mock_embedding = Mock()
        mock_embedding.embedding = [0.1, 0.2, 0.3]
        mock_embeddings.return_value = [mock_embedding]
        
        result = await handler.lookup_medical_information("test query")
        
        # Should only return new information
        assert "New medical information" in result
        assert "Already seen information" not in result
    
    def test_register_with_agent(self):
        """Test registering function tools with an agent"""
        handler = MedicalRAGHandler(index_path="/mock", data_path="/mock")
        mock_agent = Mock()
        
        handler.register_with_agent(mock_agent)
        
        # Verify function tools were added to agent
        assert hasattr(mock_agent, 'lookup_procedure_info')
        assert hasattr(mock_agent, 'lookup_medication_info')
        assert hasattr(mock_agent, 'lookup_symptom_guidance')
        assert hasattr(mock_agent, 'lookup_recovery_timeline')
        assert hasattr(mock_agent, 'medical_rag_handler')
        assert mock_agent.medical_rag_handler == handler


class TestFunctionTools:
    """Tests for RAG function tools"""
    
    @pytest.mark.asyncio
    async def test_lookup_procedure_info_with_results(self):
        """Test procedure info lookup with results"""
        handler = MedicalRAGHandler(index_path="/mock", data_path="/mock")
        mock_agent = Mock()
        mock_ctx = Mock()
        mock_ctx.agent = mock_agent
        mock_ctx.session.generate_reply = AsyncMock()
        
        # Mock the lookup to return information
        handler.lookup_medical_information = AsyncMock(return_value="Venous malformation treatment involves...")
        handler._handle_thinking = AsyncMock()
        
        handler.register_with_agent(mock_agent)
        
        # Call the function tool
        result = await mock_agent.lookup_procedure_info(mock_ctx, "venous malformation", "recovery time")
        
        # Verify thinking was handled
        handler._handle_thinking.assert_called_once_with(mock_agent)
        
        # Verify lookup was called with correct query
        handler.lookup_medical_information.assert_called_once_with("procedure venous malformation recovery time")
        
        # Verify response was generated
        mock_ctx.session.generate_reply.assert_called_once()
        call_args = mock_ctx.session.generate_reply.call_args
        assert "venous malformation" in call_args.kwargs['instructions']
        assert "Venous malformation treatment involves..." in call_args.kwargs['instructions']
        
        assert result == "Provided information about venous malformation"
    
    @pytest.mark.asyncio
    async def test_lookup_procedure_info_no_results(self):
        """Test procedure info lookup with no results"""
        handler = MedicalRAGHandler(index_path="/mock", data_path="/mock")
        mock_agent = Mock()
        mock_ctx = Mock()
        mock_ctx.agent = mock_agent
        mock_ctx.session.generate_reply = AsyncMock()
        
        # Mock the lookup to return no information
        handler.lookup_medical_information = AsyncMock(return_value="")
        handler._handle_thinking = AsyncMock()
        
        handler.register_with_agent(mock_agent)
        
        result = await mock_agent.lookup_procedure_info(mock_ctx, "unknown procedure")
        
        # Should generate fallback response
        mock_ctx.session.generate_reply.assert_called_once()
        call_args = mock_ctx.session.generate_reply.call_args
        assert "don't have specific information" in call_args.kwargs['instructions']
        
        assert result == "No specific procedure information found"
    
    @pytest.mark.asyncio
    async def test_lookup_symptom_guidance(self):
        """Test symptom guidance lookup"""
        handler = MedicalRAGHandler(index_path="/mock", data_path="/mock")
        mock_agent = Mock()
        mock_ctx = Mock()
        mock_ctx.agent = mock_agent
        mock_ctx.session.generate_reply = AsyncMock()
        
        handler.lookup_medical_information = AsyncMock(return_value="Swelling is normal after procedure...")
        handler._handle_thinking = AsyncMock()
        
        handler.register_with_agent(mock_agent)
        
        result = await mock_agent.lookup_symptom_guidance(mock_ctx, "swelling")
        
        # Verify lookup query format
        handler.lookup_medical_information.assert_called_once_with("symptom swelling post-operative recovery")
        
        # Verify response contains symptom information
        mock_ctx.session.generate_reply.assert_called_once()
        call_args = mock_ctx.session.generate_reply.call_args
        assert "swelling" in call_args.kwargs['instructions']
        assert "Swelling is normal after procedure..." in call_args.kwargs['instructions']
        
        assert result == "Provided guidance about swelling"


class TestSampleMedicalKnowledge:
    """Tests for sample medical knowledge creation"""
    
    def test_create_sample_medical_knowledge(self):
        """Test creation of sample medical knowledge"""
        knowledge = create_sample_medical_knowledge()
        
        assert isinstance(knowledge, dict)
        assert len(knowledge) > 0
        
        # Verify all values are strings (medical information)
        for uuid, info in knowledge.items():
            assert isinstance(uuid, str)
            assert isinstance(info, str)
            assert len(info) > 10  # Should be substantive medical information
        
        # Verify it contains expected medical topics
        all_info = " ".join(knowledge.values()).lower()
        assert "venous malformation" in all_info
        assert "compression" in all_info
        assert "ibuprofen" in all_info
        assert "ekg" in all_info


class TestMedicalAnnoyIndex:
    """Tests for MedicalAnnoyIndex wrapper"""
    
    @patch('annoy.AnnoyIndex')
    @patch('builtins.open')
    @patch('pickle.load')
    def test_load_index(self, mock_pickle, mock_open, mock_annoy):
        """Test loading Annoy index"""
        # Mock metadata
        mock_metadata = Mock()
        mock_metadata.f = 1536
        mock_metadata.metric = 'angular'
        mock_metadata.userdata = {0: "uuid1", 1: "uuid2"}
        mock_pickle.return_value = mock_metadata
        
        # Mock Annoy index
        mock_index_instance = Mock()
        mock_annoy.return_value = mock_index_instance
        
        index = MedicalAnnoyIndex.load("/mock/path")
        
        # Verify index was loaded correctly
        mock_annoy.assert_called_once_with(1536, 'angular')
        mock_index_instance.load.assert_called_once()
        
        assert index._index == mock_index_instance
        assert index._filedata == mock_metadata
    
    def test_query_result_creation(self):
        """Test creation of query results"""
        result = MedicalQueryResult(userdata="test-uuid", distance=0.5)
        
        assert result.userdata == "test-uuid"
        assert result.distance == 0.5