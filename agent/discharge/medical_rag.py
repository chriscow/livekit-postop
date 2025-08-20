"""
Medical RAG (Retrieval Augmented Generation) system for PostOp AI

Provides medical knowledge lookup capabilities during follow-up calls.
Based on the LiveKit RAG example but focused on medical and procedure-specific knowledge.
"""
import json
import logging
import pickle
import random
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict, Any, Literal
from collections.abc import Iterable
from dataclasses import dataclass

import annoy
from livekit.agents import Agent, RunContext, function_tool
from livekit.plugins import openai

logger = logging.getLogger("medical-rag")

# RAG Index Types and Classes
Metric = Literal["angular", "euclidean", "manhattan", "hamming", "dot"]
ANNOY_FILE = "index.annoy"
METADATA_FILE = "metadata.pkl"


@dataclass
class MedicalItem:
    i: int
    userdata: Any
    vector: list[float]


@dataclass
class _FileData:
    f: int
    metric: Metric
    userdata: dict[int, Any]


@dataclass
class MedicalQueryResult:
    userdata: Any
    distance: float


class MedicalAnnoyIndex:
    """Annoy index wrapper for medical knowledge"""
    
    def __init__(self, index: annoy.AnnoyIndex, filedata: _FileData) -> None:
        self._index = index
        self._filedata = filedata

    @classmethod
    def load(cls, path: str) -> "MedicalAnnoyIndex":
        p = Path(path)
        index_path = p / ANNOY_FILE
        metadata_path = p / METADATA_FILE

        with open(metadata_path, "rb") as f:
            metadata: _FileData = pickle.load(f)

        index = annoy.AnnoyIndex(metadata.f, metadata.metric)
        index.load(str(index_path))
        return cls(index, metadata)

    @property
    def size(self) -> int:
        return self._index.get_n_items()

    def items(self) -> Iterable[MedicalItem]:
        for i in range(self._index.get_n_items()):
            item = MedicalItem(
                i=i,
                userdata=self._filedata.userdata[i],
                vector=self._index.get_item_vector(i),
            )
            yield item

    def query(
        self, vector: list[float], n: int, search_k: int = -1
    ) -> list[MedicalQueryResult]:
        ids = self._index.get_nns_by_vector(
            vector, n, search_k=search_k, include_distances=True
        )
        return [
            MedicalQueryResult(userdata=self._filedata.userdata[i], distance=distance)
            for i, distance in zip(*ids)
        ]


class ThinkingStyle(Enum):
    """How to handle thinking delays during RAG lookups"""
    NONE = "none"
    MESSAGE = "message"
    LLM = "llm"


DEFAULT_THINKING_MESSAGES = [
    "Let me look that up for you...",
    "One moment while I check the medical guidelines...",
    "I'll find that information in our medical database...",
    "Just a second while I search our knowledge base...",
    "Looking into that medical question now..."
]

DEFAULT_THINKING_PROMPT = "Generate a very short, caring message to indicate that we're looking up medical information to help the patient"


class MedicalRAGHandler:
    """
    Handles medical knowledge retrieval for PostOp AI follow-up calls
    
    Provides function tools for agents to lookup:
    - Procedure-specific information
    - Post-operative care guidelines
    - Medication information
    - Symptom guidance
    - Recovery timelines
    """
    
    def __init__(
        self,
        index_path: str,
        data_path: str,
        thinking_style: ThinkingStyle = ThinkingStyle.MESSAGE,
        thinking_messages: Optional[List[str]] = None,
        thinking_prompt: Optional[str] = None,
        embeddings_dimension: int = 1536,
        embeddings_model: str = "text-embedding-3-small"
    ):
        """
        Initialize the medical RAG handler
        
        Args:
            index_path: Path to the Annoy index directory
            data_path: Path to the pickled medical data file
            thinking_style: How to handle delays during lookups
            thinking_messages: Custom thinking messages
            thinking_prompt: Custom thinking prompt for LLM style
            embeddings_dimension: Dimension of embeddings
            embeddings_model: OpenAI model for embeddings
        """
        self._index_path = Path(index_path)
        self._data_path = Path(data_path)
        self._thinking_style = thinking_style
        self._thinking_messages = thinking_messages or DEFAULT_THINKING_MESSAGES
        self._thinking_prompt = thinking_prompt or DEFAULT_THINKING_PROMPT
        self._embeddings_dimension = embeddings_dimension
        self._embeddings_model = embeddings_model
        
        # Track previously seen results to avoid repetition
        self._seen_results = set()
        
        # Load index and data
        try:
            if self._index_path.exists() and self._data_path.exists():
                self._annoy_index = MedicalAnnoyIndex.load(str(self._index_path))
                with open(self._data_path, "rb") as f:
                    self._medical_knowledge = pickle.load(f)
                logger.info(f"Loaded medical RAG database with {self._annoy_index.size} entries")
            else:
                logger.warning(f"Medical RAG database not found at {self._index_path} or {self._data_path}")
                self._annoy_index = None
                self._medical_knowledge = {}
        except Exception as e:
            logger.error(f"Failed to load medical RAG database: {e}")
            self._annoy_index = None
            self._medical_knowledge = {}
    
    async def _handle_thinking(self, agent: Agent) -> None:
        """Handle the thinking phase based on configured style"""
        if self._thinking_style == ThinkingStyle.NONE:
            return
            
        elif self._thinking_style == ThinkingStyle.MESSAGE:
            await agent.session.say(random.choice(self._thinking_messages))
            
        elif self._thinking_style == ThinkingStyle.LLM:
            # Create a thinking message using the LLM
            response = await agent._llm.complete(self._thinking_prompt)
            await agent.session.say(response.text)
    
    async def lookup_medical_information(self, query: str, max_results: int = 2) -> str:
        """
        Look up medical information based on a query
        
        Args:
            query: The medical question or topic to search for
            max_results: Maximum number of results to return
            
        Returns:
            Relevant medical information or empty string if nothing found
        """
        if not self._annoy_index:
            logger.warning("Medical RAG database not available")
            return ""
        
        try:
            # Generate embeddings for the query
            query_embedding = await openai.create_embeddings(
                input=[query],
                model=self._embeddings_model,
                dimensions=self._embeddings_dimension,
            )
            
            # Query the index for more results than needed to filter seen ones
            all_results = self._annoy_index.query(
                query_embedding[0].embedding, n=max_results * 2
            )
            
            # Filter out previously seen results
            new_results = [
                r for r in all_results if r.userdata not in self._seen_results
            ]
            
            if not new_results:
                # If no new results, clear seen set and try again
                self._seen_results.clear()
                new_results = all_results[:max_results]
            else:
                new_results = new_results[:max_results]
            
            # Build context from relevant medical information
            context_parts = []
            for result in new_results:
                # Mark as seen
                self._seen_results.add(result.userdata)
                
                # Get the medical information
                medical_info = self._medical_knowledge.get(result.userdata, "")
                if medical_info:
                    context_parts.append(medical_info)
            
            if not context_parts:
                return ""
            
            # Combine all context
            full_context = "\n\n".join(context_parts)
            logger.info(f"Found medical information for query: {query}")
            
            return full_context
            
        except Exception as e:
            logger.error(f"Error looking up medical information: {e}")
            return ""
    
    def register_with_agent(self, agent: Agent) -> None:
        """
        Register medical lookup function tools with an agent
        
        Args:
            agent: The agent to enhance with medical RAG capabilities
        """
        # Create function tools for medical lookup
        
        @function_tool
        async def lookup_procedure_info(ctx: RunContext, procedure: str, question: str = ""):
            """
            Look up information about a specific medical procedure
            
            Args:
                procedure: Name of the procedure (e.g., "venous malformation treatment")
                question: Specific question about the procedure
            """
            query = f"procedure {procedure} {question}".strip()
            
            await self._handle_thinking(ctx.agent)
            medical_info = await self.lookup_medical_information(query)
            
            if medical_info:
                await ctx.session.generate_reply(
                    instructions=f"""
                    The patient is asking about the procedure: {procedure}.
                    {f"Specific question: {question}" if question else ""}
                    
                    Relevant medical information:
                    {medical_info}
                    
                    Provide a clear, helpful response based on this information. 
                    Be caring and reassuring while being medically accurate.
                    """
                )
                return f"Provided information about {procedure}"
            else:
                await ctx.session.generate_reply(
                    instructions=f"I don't have specific information about {procedure} in my database. I recommend contacting your healthcare provider for detailed information about this procedure."
                )
                return "No specific procedure information found"
        
        @function_tool
        async def lookup_medication_info(ctx: RunContext, medication: str, question: str = ""):
            """
            Look up information about medications
            
            Args:
                medication: Name of the medication
                question: Specific question about the medication
            """
            query = f"medication {medication} {question}".strip()
            
            await self._handle_thinking(ctx.agent)
            medical_info = await self.lookup_medical_information(query)
            
            if medical_info:
                await ctx.session.generate_reply(
                    instructions=f"""
                    The patient is asking about the medication: {medication}.
                    {f"Specific question: {question}" if question else ""}
                    
                    Relevant medical information:
                    {medical_info}
                    
                    Provide helpful information about this medication. Always remind them to follow their doctor's specific instructions and contact their healthcare provider with concerns.
                    """
                )
                return f"Provided information about {medication}"
            else:
                await ctx.session.generate_reply(
                    instructions=f"I don't have specific information about {medication} in my database. Please follow the instructions on your medication bottle and contact your healthcare provider or pharmacist with any questions."
                )
                return "No specific medication information found"
        
        @function_tool
        async def lookup_symptom_guidance(ctx: RunContext, symptom: str):
            """
            Look up guidance about post-operative symptoms
            
            Args:
                symptom: The symptom the patient is experiencing
            """
            query = f"symptom {symptom} post-operative recovery"
            
            await self._handle_thinking(ctx.agent)
            medical_info = await self.lookup_medical_information(query)
            
            if medical_info:
                await ctx.session.generate_reply(
                    instructions=f"""
                    The patient is experiencing: {symptom}
                    
                    Relevant medical guidance:
                    {medical_info}
                    
                    Provide helpful guidance about this symptom. Always emphasize when they should contact their healthcare provider, especially for concerning symptoms.
                    """
                )
                return f"Provided guidance about {symptom}"
            else:
                await ctx.session.generate_reply(
                    instructions=f"I don't have specific guidance about {symptom} in my database. If you're concerned about this symptom, especially if it's severe, worsening, or accompanied by other symptoms, please contact your healthcare provider promptly."
                )
                return "No specific symptom guidance found"
        
        @function_tool
        async def lookup_recovery_timeline(ctx: RunContext, procedure: str, activity: str = ""):
            """
            Look up recovery timeline and activity restrictions
            
            Args:
                procedure: The procedure they had
                activity: Specific activity they're asking about
            """
            query = f"recovery timeline {procedure} {activity}".strip()
            
            await self._handle_thinking(ctx.agent)
            medical_info = await self.lookup_medical_information(query)
            
            if medical_info:
                await ctx.session.generate_reply(
                    instructions=f"""
                    The patient is asking about recovery timeline for: {procedure}
                    {f"Specific activity: {activity}" if activity else ""}
                    
                    Relevant recovery information:
                    {medical_info}
                    
                    Provide helpful information about the recovery timeline. Always remind them that individual recovery varies and they should follow their doctor's specific instructions.
                    """
                )
                return f"Provided recovery timeline for {procedure}"
            else:
                await ctx.session.generate_reply(
                    instructions=f"I don't have specific recovery timeline information for {procedure} in my database. Recovery times can vary greatly between individuals. Please follow your discharge instructions and contact your healthcare provider for specific guidance about your recovery."
                )
                return "No specific recovery timeline found"
        
        # Add the function tools to the agent
        agent.lookup_procedure_info = lookup_procedure_info.__get__(agent)
        agent.lookup_medication_info = lookup_medication_info.__get__(agent)
        agent.lookup_symptom_guidance = lookup_symptom_guidance.__get__(agent)
        agent.lookup_recovery_timeline = lookup_recovery_timeline.__get__(agent)
        
        # Store reference to RAG handler
        agent.medical_rag_handler = self
        
        logger.info("Registered medical RAG function tools with agent")


def create_sample_medical_knowledge() -> Dict[str, str]:
    """
    Create comprehensive medical knowledge base for testing/demo purposes
    
    Returns:
        Dictionary mapping UUIDs to medical information strings
    """
    import uuid
    
    sample_knowledge = {
        # Venous Malformation Specific
        str(uuid.uuid4()): "Venous malformation treatment involves sclerotherapy with bleomycin to close abnormal blood vessels. Recovery typically takes 2-4 weeks with gradual improvement in symptoms.",
        
        str(uuid.uuid4()): "Post-operative compression bandages should remain in place for 24 hours after venous malformation treatment, then worn as much as tolerated for 7 days to reduce swelling and support healing.",
        
        str(uuid.uuid4()): "Ibuprofen is commonly prescribed after venous malformation procedures for both pain relief and anti-inflammatory effects. Take as directed for 7 days regardless of pain level as it helps reduce procedure-related inflammation.",
        
        str(uuid.uuid4()): "EKG leads and adhesive should not be removed for 48 hours after bleomycin treatment due to potential cardiac monitoring needs and skin sensitivity from the procedure.",
        
        str(uuid.uuid4()): "Normal post-operative symptoms after venous malformation treatment include mild swelling, bruising, and temporary skin discoloration at the treatment site. Contact healthcare provider for fever over 100.5°F, severe pain, or signs of infection.",
        
        str(uuid.uuid4()): "Activity restrictions after venous malformation treatment typically include minimal weight-bearing for 48 hours, walking only for 7 days, then gradual return to normal activities. Elevate the treated extremity when possible.",
        
        str(uuid.uuid4()): "Bathing instructions post-procedure: may shower the day after treatment, but avoid bathing or swimming for 5 days to prevent infection and allow proper healing of the treatment site.",
        
        str(uuid.uuid4()): "Return to school or daycare is typically allowed 7 days after venous malformation treatment, provided the child is feeling well and any activity restrictions are manageable in that environment.",
        
        # General Post-Operative Care
        str(uuid.uuid4()): "Post-operative wound care: Keep incision sites clean and dry. Change dressings as instructed. Look for signs of infection including increased redness, warmth, swelling, or purulent drainage.",
        
        str(uuid.uuid4()): "Normal post-surgical healing: Mild pain, swelling, and bruising are expected for 3-7 days. Pain should gradually decrease. Contact healthcare provider if pain worsens or doesn't improve after several days.",
        
        str(uuid.uuid4()): "Post-operative diet: Start with clear liquids and advance as tolerated. Stay hydrated. Avoid alcohol if taking pain medications. Some nausea is normal for 24-48 hours after anesthesia.",
        
        str(uuid.uuid4()): "Post-operative activity: Gradual return to normal activities as directed. Avoid heavy lifting, strenuous exercise, or activities that strain the surgical site until cleared by your healthcare provider.",
        
        # Pain Management
        str(uuid.uuid4()): "Pain management after surgery: Take pain medications as prescribed, even if pain is mild, to stay ahead of discomfort. Ice packs for 15-20 minutes at a time can help reduce swelling and pain.",
        
        str(uuid.uuid4()): "NSAIDs like ibuprofen: Effective for reducing both pain and inflammation after procedures. Take with food to prevent stomach upset. Follow dosing instructions carefully.",
        
        str(uuid.uuid4()): "Acetaminophen (Tylenol): Safe for most patients and can be used with other pain medications. Do not exceed maximum daily dose. Check other medications to avoid doubling acetaminophen intake.",
        
        # Infection Prevention
        str(uuid.uuid4()): "Signs of infection: Fever over 100.5°F (38°C), increasing redness around incision, warmth, swelling, pus or unusual drainage, red streaking from wound site. Seek immediate medical attention if these occur.",
        
        str(uuid.uuid4()): "Preventing infection: Wash hands before touching surgical sites. Keep wounds clean and dry. Take antibiotics exactly as prescribed if given. Don't apply unauthorized ointments or creams.",
        
        # Swelling and Bruising
        str(uuid.uuid4()): "Post-operative swelling: Peak swelling typically occurs 2-3 days after surgery and gradually improves. Elevation of the affected area above heart level helps reduce swelling.",
        
        str(uuid.uuid4()): "Bruising after procedures: Normal and expected, especially in vascular procedures. Bruising may worsen for 2-3 days before improving. Color changes from purple to yellow-green indicate normal healing.",
        
        # Emergency Symptoms
        str(uuid.uuid4()): "Emergency symptoms requiring immediate care: Difficulty breathing, chest pain, severe bleeding that won't stop with pressure, signs of severe allergic reaction, loss of consciousness, severe persistent vomiting.",
        
        str(uuid.uuid4()): "When to call your doctor: Persistent fever, worsening pain despite medication, unusual or concerning symptoms, questions about your recovery progress, problems with medications.",
        
        # Medication Information
        str(uuid.uuid4()): "Toradol (ketorolac): Powerful anti-inflammatory given during procedures. Effects last 6-8 hours. Wait 8 hours after last dose before taking other NSAIDs to avoid complications.",
        
        str(uuid.uuid4()): "Anticoagulation and procedures: Patients on blood thinners need special timing considerations. Follow specific instructions about when to resume medications after procedures.",
        
        # Pediatric Considerations
        str(uuid.uuid4()): "Pediatric post-operative care: Children may have different pain expressions. Watch for changes in eating, sleeping, or behavior. Comfort measures like favorite toys or blankets can help recovery.",
        
        str(uuid.uuid4()): "Return to school after procedures: Consider child's energy level, any activity restrictions, ability to participate in normal school activities, and whether they can communicate their needs to teachers.",
        
        # Recovery Timeline
        str(uuid.uuid4()): "Recovery milestones: Day 1-2: Focus on rest and basic care. Day 3-7: Gradual activity increase. Week 2-4: Most normal activities resume. Full healing: 4-8 weeks depending on procedure.",
        
        str(uuid.uuid4()): "Factors affecting recovery: Age, overall health, procedure complexity, following post-operative instructions, adequate rest and nutrition, avoiding complications like infection.",
        
        # Compression Therapy
        str(uuid.uuid4()): "Compression garments: Apply gentle, consistent pressure to reduce swelling and support healing tissues. Should be snug but not painful. Remove if numbness, tingling, or color changes occur.",
        
        str(uuid.uuid4()): "Compression therapy duration: Typically worn continuously for first 24-48 hours, then as much as tolerated for specified period. Gradually reduce wearing time as healing progresses.",
        
        # Follow-up Care
        str(uuid.uuid4()): "Follow-up appointments: Essential for monitoring healing progress, removing sutures if needed, addressing concerns, and planning long-term care. Don't skip scheduled visits.",
        
        str(uuid.uuid4()): "Between appointments: Keep a log of symptoms, questions, or concerns to discuss at next visit. Take photos of healing sites if instructed for telemedicine consultations."
    }
    
    return sample_knowledge


async def build_sample_medical_rag_database(output_dir: str = "data/medical_rag"):
    """
    Build a sample medical RAG database for testing/demo purposes
    
    Args:
        output_dir: Directory to save the database files
    """
    try:
        import numpy as np
        import os
        from dotenv import load_dotenv
        
        # Load environment variables
        load_dotenv()
        
        if not os.getenv('OPENAI_API_KEY'):
            logger.error("OPENAI_API_KEY not found in environment")
            return
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Create sample knowledge
        knowledge = create_sample_medical_knowledge()
        
        # Generate embeddings for each piece of knowledge
        import openai as openai_client
        
        embeddings = []
        knowledge_list = list(knowledge.items())
        
        logger.info(f"Generating embeddings for {len(knowledge_list)} medical knowledge items...")
        
        # Create OpenAI client
        client = openai_client.AsyncOpenAI()
        
        for uuid, text in knowledge_list:
            response = await client.embeddings.create(
                input=[text],
                model="text-embedding-3-small",
                dimensions=1536
            )
            embeddings.append(response.data[0].embedding)
        
        # Build Annoy index
        dimension = 1536
        index = annoy.AnnoyIndex(dimension, 'angular')
        userdata = {}
        
        for i, ((uuid, text), embedding) in enumerate(zip(knowledge_list, embeddings)):
            index.add_item(i, embedding)
            userdata[i] = uuid
        
        index.build(10)  # 10 trees
        
        # Save index
        index_path = output_path / ANNOY_FILE
        index.save(str(index_path))
        
        # Save metadata
        metadata = _FileData(f=dimension, metric='angular', userdata=userdata)
        metadata_path = output_path / METADATA_FILE
        with open(metadata_path, "wb") as f:
            pickle.dump(metadata, f)
        
        # Save knowledge dictionary
        knowledge_path = output_path / "knowledge.pkl"
        with open(knowledge_path, "wb") as f:
            pickle.dump(knowledge, f)
        
        logger.info(f"Built sample medical RAG database in {output_path}")
        logger.info(f"  - Index: {index_path}")
        logger.info(f"  - Metadata: {metadata_path}")
        logger.info(f"  - Knowledge: {knowledge_path}")
        
    except ImportError:
        logger.error("Building RAG database requires numpy and openai packages")
    except Exception as e:
        logger.error(f"Error building medical RAG database: {e}")


if __name__ == "__main__":
    # Build sample database for testing
    import asyncio
    
    async def main():
        await build_sample_medical_rag_database()
    
    asyncio.run(main())