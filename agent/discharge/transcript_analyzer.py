"""
LLM-Based Transcript Analyzer for PostOp AI

This module analyzes discharge instruction transcripts using LLM intelligence
to determine optimal follow-up call scheduling and content personalization.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from livekit.plugins import openai
from shared.memory import RedisMemory


logger = logging.getLogger("transcript-analyzer")


class CallUrgency(Enum):
    """Urgency levels for follow-up calls"""
    URGENT = 1      # Critical instructions requiring immediate follow-up
    IMPORTANT = 2   # Standard discharge instructions  
    ROUTINE = 3     # General wellness checks


class CallTiming(Enum):
    """Standard timing patterns for calls"""
    IMMEDIATE = "immediate"           # Within 2-4 hours
    NEXT_DAY = "next_day"            # 18-24 hours after discharge
    TWO_DAYS = "two_days"            # 36-48 hours after discharge  
    THREE_DAYS = "three_days"        # 60-72 hours after discharge
    ONE_WEEK = "one_week"            # 7 days after discharge
    TWO_WEEKS = "two_weeks"          # 14 days after discharge


@dataclass
class AnalyzedInstruction:
    """Individual instruction analysis result"""
    original_text: str
    instruction_type: str
    key_points: List[str]
    urgency: CallUrgency
    recommended_timing: CallTiming
    personalized_prompt: str
    requires_follow_up: bool
    clinical_flags: List[str]  # Warning signs to monitor


@dataclass 
class CallRecommendation:
    """Recommended call with LLM-determined scheduling"""
    call_type: str
    scheduled_timing: CallTiming  
    priority: int
    llm_prompt: str
    instruction_references: List[str]
    wellness_focus: bool
    language_specific_notes: str


@dataclass
class TranscriptAnalysis:
    """Complete analysis result from LLM processing"""
    patient_id: str
    patient_name: str
    patient_language: str
    session_id: str
    analyzed_instructions: List[AnalyzedInstruction]
    call_recommendations: List[CallRecommendation]
    overall_complexity: str  # simple, moderate, complex
    special_considerations: List[str]
    estimated_recovery_timeline: str
    analysis_confidence: float


class TranscriptAnalyzer:
    """LLM-powered analyzer for discharge instruction transcripts"""
    
    def __init__(self):
        self.llm = openai.LLM(model="gpt-4")
        self.memory = RedisMemory()
        
    async def analyze_discharge_transcript(
        self, 
        session_id: str,
        patient_name: str,
        patient_language: str,
        collected_instructions: List[Dict[str, Any]],
        original_instructions: List[Dict[str, Any]] = None
    ) -> TranscriptAnalysis:
        """
        Perform comprehensive LLM analysis of discharge instructions
        
        Args:
            session_id: Discharge session identifier
            patient_name: Patient's name for personalization
            patient_language: Patient's preferred language
            collected_instructions: Instructions collected during discharge
            original_instructions: Original English instructions (if translated)
            
        Returns:
            Complete analysis with call recommendations
        """
        logger.info(f"Starting LLM analysis for session {session_id}, patient {patient_name}")
        
        # Use original instructions if available (from translation workflow)
        instructions_to_analyze = original_instructions or collected_instructions
        
        if not instructions_to_analyze:
            logger.warning(f"No instructions to analyze for session {session_id}")
            return self._create_minimal_analysis(session_id, patient_name, patient_language)
        
        # Prepare instruction text for LLM analysis
        instruction_texts = []
        for i, instruction in enumerate(instructions_to_analyze, 1):
            text = instruction.get('text', '')
            inst_type = instruction.get('type', 'general')
            instruction_texts.append(f"{i}. [{inst_type}] {text}")
        
        combined_instructions = "\\n".join(instruction_texts)
        
        # Generate comprehensive analysis using LLM
        analysis_prompt = self._create_analysis_prompt(
            patient_name, patient_language, combined_instructions
        )
        
        try:
            # Get structured analysis from LLM
            analysis_response = await self._get_llm_analysis(analysis_prompt)
            
            # Parse LLM response into structured data
            analysis = self._parse_llm_response(
                analysis_response, session_id, patient_name, patient_language, instructions_to_analyze
            )
            
            # Store analysis results in Redis for later reference
            self._store_analysis(session_id, analysis)
            
            logger.info(f"Completed LLM analysis for {patient_name}: {len(analysis.call_recommendations)} calls recommended")
            return analysis
            
        except Exception as e:
            logger.error(f"LLM analysis failed for session {session_id}: {e}")
            return self._create_fallback_analysis(session_id, patient_name, patient_language, instructions_to_analyze)
    
    def _create_analysis_prompt(self, patient_name: str, patient_language: str, instructions: str) -> str:
        """Create comprehensive analysis prompt for the LLM"""
        
        return f"""You are a medical AI assistant specialized in analyzing patient discharge instructions to determine optimal follow-up call scheduling.

PATIENT INFORMATION:
- Name: {patient_name}
- Preferred Language: {patient_language}

DISCHARGE INSTRUCTIONS TO ANALYZE:
{instructions}

ANALYSIS REQUIREMENTS:

1. **Instruction Analysis**: For each instruction, identify:
   - Key medical points that need follow-up
   - Urgency level (1=urgent, 2=important, 3=routine)
   - Recommended follow-up timing (immediate, next_day, two_days, three_days, one_week, two_weeks)
   - Any warning signs or complications to monitor

2. **Call Scheduling Strategy**: Determine:
   - How many follow-up calls would be most effective
   - What timing would maximize patient compliance
   - Whether calls should focus on specific instructions or general wellness
   - How to personalize calls for this patient's language and cultural background

3. **Risk Assessment**: Consider:
   - Complexity of instructions (simple/moderate/complex)
   - Patient's likely compliance challenges
   - Critical timeline elements (medication schedules, bandage changes, etc.)
   - Any red flags requiring urgent attention

4. **Personalization**: Account for:
   - Language preferences and communication style
   - Cultural considerations for {patient_language} speakers
   - Appropriate times for calls based on cultural norms
   - Family involvement expectations

OUTPUT FORMAT: Please provide your analysis as a JSON object with this structure:

{{
  "instruction_analysis": [
    {{
      "instruction_number": 1,
      "original_text": "exact text from instruction",
      "instruction_type": "medication|activity|followup|warning|general",
      "key_points": ["point 1", "point 2"],
      "urgency": 1-3,
      "recommended_timing": "immediate|next_day|two_days|three_days|one_week|two_weeks",
      "clinical_flags": ["warning sign 1", "warning sign 2"],
      "requires_follow_up": true/false
    }}
  ],
  "call_recommendations": [
    {{
      "call_type": "compression_check|medication_reminder|wellness_check|activity_guidance|general_followup",
      "scheduled_timing": "next_day|two_days|etc",
      "priority": 1-3,
      "instruction_references": ["instruction 1", "instruction 2"],
      "wellness_focus": true/false,
      "personalized_prompt": "Specific call script focusing on this patient's needs and language",
      "language_specific_notes": "Cultural considerations for {patient_language} speakers"
    }}
  ],
  "overall_assessment": {{
    "complexity": "simple|moderate|complex",
    "special_considerations": ["consideration 1", "consideration 2"],
    "estimated_recovery_timeline": "description of expected recovery progression",
    "analysis_confidence": 0.0-1.0
  }}
}}

Please analyze thoughtfully and provide specific, actionable recommendations for this patient's follow-up care."""

    async def _get_llm_analysis(self, prompt: str) -> str:
        """Get structured analysis from LLM"""
        try:
            # Use the LLM to generate analysis
            response = await self.llm.agenerate(prompt)
            return response.content
        except Exception as e:
            logger.error(f"LLM API call failed: {e}")
            raise
    
    def _parse_llm_response(
        self, 
        llm_response: str, 
        session_id: str, 
        patient_name: str, 
        patient_language: str,
        original_instructions: List[Dict[str, Any]]
    ) -> TranscriptAnalysis:
        """Parse LLM JSON response into structured analysis object"""
        
        try:
            # Extract JSON from LLM response (handle potential markdown formatting)
            json_start = llm_response.find('{')
            json_end = llm_response.rfind('}') + 1
            
            if json_start == -1 or json_end == 0:
                raise ValueError("No JSON found in LLM response")
                
            json_str = llm_response[json_start:json_end]
            analysis_data = json.loads(json_str)
            
            # Parse analyzed instructions
            analyzed_instructions = []
            for inst_data in analysis_data.get('instruction_analysis', []):
                # Handle urgency - could be int or string
                urgency_val = inst_data.get('urgency', 3)
                if isinstance(urgency_val, str):
                    urgency_map = {'urgent': 1, 'important': 2, 'routine': 3}
                    urgency_val = urgency_map.get(urgency_val.lower(), 3)
                
                # Handle timing - could be enum value or string
                timing_val = inst_data.get('recommended_timing', 'next_day')
                if isinstance(timing_val, str) and timing_val not in [t.value for t in CallTiming]:
                    # Map common string variations
                    timing_map = {
                        'immediate': CallTiming.IMMEDIATE,
                        'next day': CallTiming.NEXT_DAY,
                        'two days': CallTiming.TWO_DAYS,
                        'three days': CallTiming.THREE_DAYS,
                        'one week': CallTiming.ONE_WEEK,
                        'two weeks': CallTiming.TWO_WEEKS,
                    }
                    timing_val = timing_map.get(timing_val.lower(), CallTiming.NEXT_DAY).value
                
                analyzed_instructions.append(AnalyzedInstruction(
                    original_text=inst_data.get('original_text', ''),
                    instruction_type=inst_data.get('instruction_type', 'general'),
                    key_points=inst_data.get('key_points', []),
                    urgency=CallUrgency(urgency_val),
                    recommended_timing=CallTiming(timing_val),
                    personalized_prompt="",  # Will be filled from call recommendations
                    requires_follow_up=inst_data.get('requires_follow_up', True),
                    clinical_flags=inst_data.get('clinical_flags', [])
                ))
            
            # Parse call recommendations  
            call_recommendations = []
            for call_data in analysis_data.get('call_recommendations', []):
                # Handle scheduled_timing - could be enum value or string
                timing_val = call_data.get('scheduled_timing', 'next_day')
                if isinstance(timing_val, str) and timing_val not in [t.value for t in CallTiming]:
                    # Map common string variations
                    timing_map = {
                        'immediate': CallTiming.IMMEDIATE,
                        'next day': CallTiming.NEXT_DAY,
                        'two days': CallTiming.TWO_DAYS,
                        'three days': CallTiming.THREE_DAYS,
                        'one week': CallTiming.ONE_WEEK,
                        'two weeks': CallTiming.TWO_WEEKS,
                    }
                    timing_val = timing_map.get(timing_val.lower(), CallTiming.NEXT_DAY).value
                
                call_recommendations.append(CallRecommendation(
                    call_type=call_data.get('call_type', 'general_followup'),
                    scheduled_timing=CallTiming(timing_val),
                    priority=call_data.get('priority', 3),
                    llm_prompt=call_data.get('personalized_prompt', ''),
                    instruction_references=call_data.get('instruction_references', []),
                    wellness_focus=call_data.get('wellness_focus', False),
                    language_specific_notes=call_data.get('language_specific_notes', '')
                ))
            
            # Parse overall assessment
            overall = analysis_data.get('overall_assessment', {})
            
            return TranscriptAnalysis(
                patient_id=f"analyzed-{session_id}",
                patient_name=patient_name,
                patient_language=patient_language,
                session_id=session_id,
                analyzed_instructions=analyzed_instructions,
                call_recommendations=call_recommendations,
                overall_complexity=overall.get('complexity', 'moderate'),
                special_considerations=overall.get('special_considerations', []),
                estimated_recovery_timeline=overall.get('estimated_recovery_timeline', ''),
                analysis_confidence=overall.get('analysis_confidence', 0.8)
            )
            
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to parse LLM response: {e}")
            logger.debug(f"LLM response was: {llm_response}")
            return self._create_fallback_analysis(session_id, patient_name, patient_language, original_instructions)
    
    def _create_minimal_analysis(self, session_id: str, patient_name: str, patient_language: str) -> TranscriptAnalysis:
        """Create minimal analysis when no instructions are available"""
        
        return TranscriptAnalysis(
            patient_id=f"minimal-{session_id}",
            patient_name=patient_name,
            patient_language=patient_language,
            session_id=session_id,
            analyzed_instructions=[],
            call_recommendations=[
                CallRecommendation(
                    call_type="wellness_check",
                    scheduled_timing=CallTiming.NEXT_DAY,
                    priority=3,
                    llm_prompt=f"Hello {patient_name}, this is a courtesy call from PostOp AI to check how you're feeling after your procedure. How are you doing today?",
                    instruction_references=[],
                    wellness_focus=True,
                    language_specific_notes=f"Use appropriate greeting for {patient_language} speakers"
                )
            ],
            overall_complexity="simple",
            special_considerations=["No specific discharge instructions recorded"],
            estimated_recovery_timeline="Standard recovery expected",
            analysis_confidence=0.5
        )
    
    def _create_fallback_analysis(
        self, 
        session_id: str, 
        patient_name: str, 
        patient_language: str,
        instructions: List[Dict[str, Any]]
    ) -> TranscriptAnalysis:
        """Create fallback analysis when LLM analysis fails"""
        
        # Create basic analyzed instructions
        analyzed_instructions = []
        for i, instruction in enumerate(instructions):
            analyzed_instructions.append(AnalyzedInstruction(
                original_text=instruction.get('text', ''),
                instruction_type=instruction.get('type', 'general'),
                key_points=[instruction.get('text', '')[:100]],
                urgency=CallUrgency.IMPORTANT,
                recommended_timing=CallTiming.NEXT_DAY,
                personalized_prompt="",
                requires_follow_up=True,
                clinical_flags=[]
            ))
        
        # Create basic call recommendations
        call_recommendations = [
            CallRecommendation(
                call_type="general_followup", 
                scheduled_timing=CallTiming.NEXT_DAY,
                priority=2,
                llm_prompt=f"Hello {patient_name}, I'm calling to follow up on your discharge instructions and see how you're feeling.",
                instruction_references=[f"instruction {i+1}" for i in range(len(instructions))],
                wellness_focus=True,
                language_specific_notes=""
            ),
            CallRecommendation(
                call_type="wellness_check",
                scheduled_timing=CallTiming.THREE_DAYS, 
                priority=3,
                llm_prompt=f"Hi {patient_name}, this is a follow-up wellness check. How has your recovery been going?",
                instruction_references=[],
                wellness_focus=True,
                language_specific_notes=""
            )
        ]
        
        return TranscriptAnalysis(
            patient_id=f"fallback-{session_id}",
            patient_name=patient_name,
            patient_language=patient_language,
            session_id=session_id,
            analyzed_instructions=analyzed_instructions,
            call_recommendations=call_recommendations,
            overall_complexity="moderate",
            special_considerations=["Analysis created using fallback method"],
            estimated_recovery_timeline="Standard recovery timeline expected",
            analysis_confidence=0.6
        )
    
    def _store_analysis(self, session_id: str, analysis: TranscriptAnalysis) -> None:
        """Store analysis results in Redis for later reference"""
        try:
            # Store complete analysis as JSON
            analysis_data = {
                "patient_id": analysis.patient_id,
                "patient_name": analysis.patient_name,  
                "patient_language": analysis.patient_language,
                "analyzed_instructions_count": len(analysis.analyzed_instructions),
                "call_recommendations_count": len(analysis.call_recommendations),
                "overall_complexity": analysis.overall_complexity,
                "special_considerations": analysis.special_considerations,
                "estimated_recovery_timeline": analysis.estimated_recovery_timeline,
                "analysis_confidence": analysis.analysis_confidence,
                "analyzed_at": datetime.now().isoformat()
            }
            
            self.memory.store_session_data(session_id, "llm_analysis", analysis_data)
            
            # Store call recommendations separately for easy access
            call_data = []
            for call in analysis.call_recommendations:
                call_data.append({
                    "call_type": call.call_type,
                    "scheduled_timing": call.scheduled_timing.value,
                    "priority": call.priority,
                    "llm_prompt": call.llm_prompt,
                    "instruction_references": call.instruction_references,
                    "wellness_focus": call.wellness_focus,
                    "language_specific_notes": call.language_specific_notes
                })
            
            self.memory.store_session_data(session_id, "call_recommendations", call_data)
            
            logger.info(f"Stored analysis results for session {session_id}")
            
        except Exception as e:
            logger.error(f"Failed to store analysis for session {session_id}: {e}")
    
    def get_stored_analysis(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve previously stored analysis from Redis"""
        try:
            analysis_data = self.memory.get_session_data(session_id, "llm_analysis")
            call_recommendations = self.memory.get_session_data(session_id, "call_recommendations")
            
            if analysis_data and call_recommendations:
                return {
                    "analysis": analysis_data,
                    "call_recommendations": call_recommendations
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to retrieve stored analysis for session {session_id}: {e}")
            return None
    
    def convert_to_call_schedule_items(
        self, 
        analysis: TranscriptAnalysis,
        discharge_time: datetime
    ) -> List[Dict[str, Any]]:
        """
        Convert LLM analysis into CallScheduleItem-compatible format
        
        Args:
            analysis: The LLM analysis results
            discharge_time: When the patient was discharged
            
        Returns:
            List of call dictionaries compatible with CallScheduler
        """
        call_items = []
        
        for call_rec in analysis.call_recommendations:
            # Calculate scheduled time based on LLM recommendation
            scheduled_time = self._calculate_call_time(discharge_time, call_rec.scheduled_timing)
            
            # Create call item dictionary
            call_item = {
                "patient_id": analysis.patient_id,
                "patient_phone": "unknown",  # Will be filled by calling code
                "patient_name": analysis.patient_name,
                "scheduled_time": scheduled_time,
                "call_type": call_rec.call_type,
                "priority": call_rec.priority,
                "llm_prompt": call_rec.llm_prompt,
                "metadata": {
                    "analysis_source": "llm_transcript_analysis",
                    "session_id": analysis.session_id, 
                    "wellness_focus": call_rec.wellness_focus,
                    "instruction_references": call_rec.instruction_references,
                    "language_specific_notes": call_rec.language_specific_notes,
                    "analysis_confidence": analysis.analysis_confidence
                }
            }
            
            call_items.append(call_item)
        
        return call_items
    
    def _calculate_call_time(self, discharge_time: datetime, timing: CallTiming) -> datetime:
        """Calculate actual call time based on timing recommendation"""
        
        timing_map = {
            CallTiming.IMMEDIATE: timedelta(hours=3),
            CallTiming.NEXT_DAY: timedelta(hours=20),  # Next evening
            CallTiming.TWO_DAYS: timedelta(hours=44),   # Two days, afternoon
            CallTiming.THREE_DAYS: timedelta(hours=68), # Three days, afternoon
            CallTiming.ONE_WEEK: timedelta(days=7),
            CallTiming.TWO_WEEKS: timedelta(days=14)
        }
        
        return discharge_time + timing_map.get(timing, timedelta(hours=20))


# Convenience function for easy integration
async def analyze_and_schedule_calls(
    session_id: str,
    patient_name: str, 
    patient_phone: str,
    patient_language: str,
    collected_instructions: List[Dict[str, Any]],
    original_instructions: List[Dict[str, Any]] = None,
    discharge_time: datetime = None
) -> Tuple[TranscriptAnalysis, List[Dict[str, Any]]]:
    """
    Convenience function to analyze transcript and generate call schedule items
    
    Returns:
        Tuple of (analysis_result, call_schedule_items)
    """
    analyzer = TranscriptAnalyzer()
    
    # Perform LLM analysis
    analysis = await analyzer.analyze_discharge_transcript(
        session_id=session_id,
        patient_name=patient_name,
        patient_language=patient_language,
        collected_instructions=collected_instructions,
        original_instructions=original_instructions
    )
    
    # Convert to call schedule items
    discharge_time = discharge_time or datetime.now()
    call_items = analyzer.convert_to_call_schedule_items(analysis, discharge_time)
    
    # Add patient phone to call items
    for call_item in call_items:
        call_item["patient_phone"] = patient_phone
    
    return analysis, call_items