"""
Formatter module for converting natural language LLM responses to structured JSON.
Uses Gemini 2.5 Flash to extract and format information from reasoning-focused responses.
"""

import json
import logging
import os
from typing import Dict, Any, Optional
import google.generativeai as genai
from pathlib import Path
from typing import Optional

# Import logging function
from .utils import log_llm_response

logger = logging.getLogger(__name__)

# Configure Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY"))
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Format type constants
FORMAT_STATE_UPDATE = "state_update"
FORMAT_CONVERSATION = "conversation"
FORMAT_NEGOTIATION_DIARY = "negotiation_diary"
FORMAT_ORDERS = "orders"
FORMAT_INITIAL_STATE = "initial_state"
FORMAT_ORDER_DIARY = "order_diary"


async def format_with_gemini_flash(
    raw_response: str, 
    format_type: str,
    power_name: Optional[str] = None,
    phase: Optional[str] = None,
    log_file_path: Optional[str] = None
) -> str:
    """
    Convert a natural language response to the required JSON format using Gemini Flash.
    
    Args:
        raw_response: The natural language response from the primary LLM
        format_type: One of the FORMAT_* constants indicating desired output format
        power_name: Optional power name for logging
        phase: Optional phase for logging
        log_file_path: Optional path to CSV log file
        
    Returns:
        JSON string in the expected format for the given type
        
    Raises:
        Exception: If formatting fails or format_type is invalid
    """
    logger.info(f"[FORMATTER] Called format_with_gemini_flash for format_type: {format_type}")
    logger.debug(f"[FORMATTER] Raw response preview: {raw_response[:200]}...")
    
    # Load the appropriate formatting prompt
    prompts_dir = Path(__file__).parent / "prompts" / "formatting"
    prompt_file = prompts_dir / f"format_{format_type}.txt"
    
    if not prompt_file.exists():
        logger.error(f"[FORMATTER] Format prompt file not found: {prompt_file}")
        raise ValueError(f"Unknown format type: {format_type}")
    
    with open(prompt_file, 'r') as f:
        format_prompt = f.read()
    
    # Replace placeholder with actual response
    format_prompt = format_prompt.replace("[RAW_RESPONSE]", raw_response)
    
    # Don't log the request separately - we'll log once after we get the response
    
    # Use Gemini Flash for formatting
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    generation_config = {
        "temperature": 0,  # Deterministic formatting
        "max_output_tokens": 4096,
    }
    
    try:
        logger.info(f"[FORMATTER] Calling Gemini Flash for {format_type} formatting")
        response = model.generate_content(
            format_prompt,
            generation_config=generation_config
        )
        
        formatted_response = response.text.strip()
        logger.debug(f"[FORMATTER] Gemini Flash response: {formatted_response[:200]}...")
        
        # Remove markdown code blocks if present
        if formatted_response.startswith("```json"):
            formatted_response = formatted_response[7:]  # Remove ```json
        elif formatted_response.startswith("```"):
            formatted_response = formatted_response[3:]  # Remove ```
            
        if formatted_response.endswith("```"):
            formatted_response = formatted_response[:-3]  # Remove trailing ```
            
        formatted_response = formatted_response.strip()
        
        # For orders format, wrap in PARSABLE OUTPUT if needed
        if format_type == FORMAT_ORDERS and "PARSABLE OUTPUT:" not in formatted_response:
            # Extract just the JSON part and wrap it
            if formatted_response.startswith("{"):
                formatted_response = f"PARSABLE OUTPUT:\n{formatted_response}"
        
        logger.info(f"[FORMATTER] Successfully formatted {format_type} response")
        
        # Log the successful formatting response
        if log_file_path:
            log_llm_response(
                log_file_path=log_file_path,
                model_name="gemini-2.5-flash",
                power_name=power_name,
                phase=phase or "unknown",
                response_type=f"format_{format_type}",
                raw_input_prompt=format_prompt,
                raw_response=formatted_response,
                success="TRUE"
            )
        
        return formatted_response
        
    except Exception as e:
        # If Gemini fails, return the original response
        # The existing parsing logic will attempt to handle it
        logger.error(f"[FORMATTER] Gemini Flash formatting failed for {format_type}: {str(e)}")
        logger.error(f"[FORMATTER] Returning original response as fallback")
        
        # Log the failed formatting attempt
        if log_file_path:
            log_llm_response(
                log_file_path=log_file_path,
                model_name="gemini-2.5-flash",
                power_name=power_name,
                phase=phase or "unknown",
                response_type=f"format_{format_type}",
                raw_input_prompt=format_prompt,
                raw_response=str(e),  # Log the error
                success=f"FAILURE: {type(e).__name__}"
            )
        
        return raw_response


def create_formatting_prompts():
    """Create the formatting prompt files if they don't exist."""
    prompts_dir = Path(__file__).parent / "prompts" / "formatting"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    
    # Format prompts with examples moved from original prompts
    format_prompts = {
        FORMAT_ORDER_DIARY: """Extract the order summary from the response below and format it as JSON.

Required JSON format:
{
  "order_summary": "Brief summary of orders and strategic intent"
}

Instructions:
- Extract the summary of what orders were given and why
- Keep it concise but informative
- Focus on the strategic intent behind the orders

Response to format:
[RAW_RESPONSE]

Return ONLY the JSON object, no other text.""",

        FORMAT_INITIAL_STATE: """Extract the initial goals and relationships from the response below and format as JSON.

Required JSON format:
{
  "initial_goals": [
    "Specific goal 1",
    "Specific goal 2",
    "Specific goal 3"
  ],
  "initial_relationships": {
    "AUSTRIA": "Enemy|Unfriendly|Neutral|Friendly|Ally",
    "ENGLAND": "Enemy|Unfriendly|Neutral|Friendly|Ally",
    "FRANCE": "Enemy|Unfriendly|Neutral|Friendly|Ally",
    "GERMANY": "Enemy|Unfriendly|Neutral|Friendly|Ally",
    "ITALY": "Enemy|Unfriendly|Neutral|Friendly|Ally",
    "RUSSIA": "Enemy|Unfriendly|Neutral|Friendly|Ally",
    "TURKEY": "Enemy|Unfriendly|Neutral|Friendly|Ally"
  }
}

Instructions:
- Extract 3-5 specific strategic goals from the reasoning
- For relationships, use ONLY: Enemy, Unfriendly, Neutral, Friendly, or Ally
- Include all 7 powers (remove yourself from the list)

Response to format:
[RAW_RESPONSE]

Return ONLY the JSON object, no other text.""",

        FORMAT_NEGOTIATION_DIARY: """Extract the negotiation analysis and format as JSON.

Required JSON format:
{
  "negotiation_summary": "Key outcomes from negotiations - what was discussed and agreed",
  "intent": "Strategic intent for upcoming orders based on negotiations",
  "updated_relationships": {
    "POWER_NAME": "Enemy|Unfriendly|Neutral|Friendly|Ally"
  }
}

Example scenarios:

Scenario 1 - Alliance forming:
{
  "negotiation_summary": "Reached agreement with Italy for DMZ in Piedmont and mutual support against Austria. England remains non-committal about channel.",
  "intent": "Will honor DMZ with Italy and support their move to Trieste while securing Belgium",
  "updated_relationships": {
    "ITALY": "Friendly",
    "ENGLAND": "Neutral",
    "AUSTRIA": "Unfriendly"
  }
}

Scenario 2 - Detecting deception:
{
  "negotiation_summary": "Germany claims they'll support me into Belgium but also told England they'd help them. Russia suspiciously quiet.",
  "intent": "Assume Germany is unreliable, prepare defensive positions",
  "updated_relationships": {
    "GERMANY": "Unfriendly",
    "RUSSIA": "Neutral"
  }
}

Scenario 3 - Coordinated attack:
{
  "negotiation_summary": "Coordinated joint attack on Turkey with Austria. Russia agrees to DMZ Black Sea.",
  "intent": "Execute agreed plan: Army Greece to Bulgaria, Fleet Aegean to Eastern Med",
  "updated_relationships": {
    "AUSTRIA": "Ally",
    "RUSSIA": "Friendly",
    "TURKEY": "Enemy"
  }
}

Instructions:
- Summarize what was actually discussed and agreed (or disagreed) upon
- State clear intent for upcoming moves based on negotiations
- Only include powers whose relationships have changed
- Use ONLY: Enemy, Unfriendly, Neutral, Friendly, or Ally

Response to format:
[RAW_RESPONSE]

Return ONLY the JSON object, no other text.""",

        FORMAT_STATE_UPDATE: """Extract the state update information and format as JSON.

Required JSON format:
{
  "reasoning": "Brief explanation of your analysis",
  "relationships": {
    "AUSTRIA": "Enemy|Unfriendly|Neutral|Friendly|Ally",
    "ENGLAND": "Enemy|Unfriendly|Neutral|Friendly|Ally",
    "FRANCE": "Enemy|Unfriendly|Neutral|Friendly|Ally",
    "GERMANY": "Enemy|Unfriendly|Neutral|Friendly|Ally",
    "ITALY": "Enemy|Unfriendly|Neutral|Friendly|Ally",
    "RUSSIA": "Enemy|Unfriendly|Neutral|Friendly|Ally",
    "TURKEY": "Enemy|Unfriendly|Neutral|Friendly|Ally"
  },
  "goals": [
    "Specific goal 1",
    "Specific goal 2",
    "Specific goal 3"
  ]
}

Example scenarios:

Scenario 1 - Early game position:
{
  "reasoning": "France moved to Channel despite promises. Germany supporting me as agreed. Focus shifting to defending homeland.",
  "relationships": {
    "AUSTRIA": "Neutral",
    "ENGLAND": "Neutral",
    "FRANCE": "Enemy",
    "GERMANY": "Friendly",
    "ITALY": "Neutral",
    "RUSSIA": "Neutral",
    "TURKEY": "Neutral"
  },
  "goals": [
    "Defend London from French fleet in Channel",
    "Secure Norway before Russia",
    "Coordinate with Germany against France"
  ]
}

Scenario 2 - Mid-game betrayal:
{
  "reasoning": "Italy broke our alliance and took Marseilles. Need new allies urgently. Germany looking strong.",
  "relationships": {
    "AUSTRIA": "Unfriendly",
    "ENGLAND": "Neutral", 
    "FRANCE": "Neutral",
    "GERMANY": "Unfriendly",
    "ITALY": "Enemy",
    "RUSSIA": "Friendly",
    "TURKEY": "Ally"
  },
  "goals": [
    "Retake Marseilles from Italy",
    "Fortify Alpine positions",
    "Support Turkey against Austria"
  ]
}

Instructions:
- Extract the strategic reasoning from the analysis
- Include ALL 7 powers in relationships (remove yourself)
- Use ONLY: Enemy, Unfriendly, Neutral, Friendly, or Ally
- Extract 2-4 specific, actionable goals

Response to format:
[RAW_RESPONSE]

Return ONLY the JSON object, no other text.""",

        FORMAT_ORDERS: """Extract the orders from the response and format them properly.

Required format:
PARSABLE OUTPUT:
{{
  "orders": ["order1", "order2", "order3"]
}}

Order format examples:
- Hold: "A PAR H"
- Move: "A PAR - MAR", "F BRE - MAO"
- Support: "A MAR S A PAR - BUR", "F MAO S F BRE - ENG"
- Convoy: "F MAO C A BRE - LON"
- Build: "A PAR B", "F BRE B"
- Disband: "A PAR D"
- Retreat: "A PAR - BUR"
- Dual-coast: "F STP/SC" (south coast), "F SPA/NC" (north coast)

Example 1 - France Spring 1901:
If the response mentions:
"I'll move army from Paris to Burgundy, fleet from Brest to Mid-Atlantic, and hold Marseilles"

Extract as:
PARSABLE OUTPUT:
{{
  "orders": [
    "A PAR - BUR",
    "F BRE - MAO",
    "A MAR H"
  ]
}}

Example 2 - Italy with supports:
If the response mentions:
"Venice attacks Trieste with support from Apulia and Ionian Sea"

Extract as:
PARSABLE OUTPUT:
{{
  "orders": [
    "A VEN - TRI",
    "A APU S A VEN - TRI",
    "F ION S A VEN - TRI"
  ]
}}

Example 3 - Build phase:
If the response mentions:
"Build army in Paris and fleet in Marseilles"

Extract as:
PARSABLE OUTPUT:
{{
  "orders": [
    "A PAR B",
    "F MAR B"
  ]
}}

Instructions:
- Extract all orders mentioned in the response
- Use exact 3-letter province codes
- Format each order exactly as shown in examples
- Include ALL units that were given orders
- Pay attention to support orders - they must reference exact moves

Response to format:
[RAW_RESPONSE]

Return in this exact format with double braces:
PARSABLE OUTPUT:
{{
  "orders": [list of order strings]
}}""",

        FORMAT_CONVERSATION: """Extract the messages from the response and format as JSON array.

Required JSON format:
[
  {
    "message_type": "global",
    "content": "Message text for all powers"
  },
  {
    "message_type": "private", 
    "recipient": "POWER_NAME",
    "content": "Private message text"
  }
]

Example 1 - Multiple messages:
If the response mentions:
"Send a global message: 'I propose we all work together against the leader'
Tell Germany privately: 'I'll support you into Denmark if you help me with Belgium'
Message Russia: 'Are you still interested in the Black Sea DMZ?'"

Extract as:
[
  {
    "message_type": "global",
    "content": "I propose we all work together against the leader"
  },
  {
    "message_type": "private",
    "recipient": "GERMANY",
    "content": "I'll support you into Denmark if you help me with Belgium"
  },
  {
    "message_type": "private",
    "recipient": "RUSSIA",
    "content": "Are you still interested in the Black Sea DMZ?"
  }
]

Example 2 - Single private message:
If the response mentions:
"Reply to Italy: 'I accept your proposal for Piedmont DMZ'"

Extract as:
[
  {
    "message_type": "private",
    "recipient": "ITALY",
    "content": "I accept your proposal for Piedmont DMZ"
  }
]

Example 3 - No messages:
If the response indicates no messages to send:

Extract as:
[]

Instructions:
- Extract each message the player wants to send
- Identify if it's meant for everyone (global) or specific power (private)
- For private messages, identify the recipient power (use uppercase: AUSTRIA, ENGLAND, FRANCE, GERMANY, ITALY, RUSSIA, TURKEY)
- Preserve the key diplomatic points but clean up formatting
- Use proper JSON string escaping for quotes
- Return empty array [] if no messages

Response to format:
[RAW_RESPONSE]

Return ONLY the JSON array, no other text."""
    }
    
    # Write all formatting prompts
    for format_type, prompt_content in format_prompts.items():
        prompt_file = prompts_dir / f"format_{format_type}.txt"
        with open(prompt_file, 'w') as f:
            f.write(prompt_content)
    
    print(f"Created {len(format_prompts)} formatting prompts in {prompts_dir}")


if __name__ == "__main__":
    # Create the formatting prompts when module is run directly
    create_formatting_prompts()