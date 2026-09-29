from pathlib import Path

# 1. Update D:\Desktop\ia de cortes\supox\.env
env_path = Path(r"D:\Desktop\ia de cortes\supox\.env")
if env_path.exists():
    env_content = env_path.read_text(encoding="utf-8")
    env_content = env_content.replace("LLM=openrouter:openrouter/free", "LLM=openrouter:deepseek/deepseek-chat")
    env_content = env_content.replace("OPENROUTER_DEFAULT_MODEL=openrouter/free", "OPENROUTER_DEFAULT_MODEL=deepseek/deepseek-chat")
    env_path.write_text(env_content, encoding="utf-8")
    print("Updated supox/.env with deepseek/deepseek-chat")

# 2. Update D:\Desktop\ia de cortes\supox\backend\src\services\openrouter_llm.py
llm_service_path = Path(r"D:\Desktop\ia de cortes\supox\backend\src\services\openrouter_llm.py")
if llm_service_path.exists():
    code = llm_service_path.read_text(encoding="utf-8")

    # Update FALLBACK_MODELS
    old_fallback = '''FALLBACK_MODELS = [
    "openrouter/free",
    "nvidia/nemotron-3.5-lightning:free",
    "meta-llama/llama-3.3-70b-instruct",
]'''
    new_fallback = '''FALLBACK_MODELS = [
    "deepseek/deepseek-chat",
    "meta-llama/llama-3.3-70b-instruct",
    "nvidia/nemotron-3.5-lightning:free",
    "openrouter/free",
]'''
    if old_fallback in code:
        code = code.replace(old_fallback, new_fallback)
        print("Updated FALLBACK_MODELS")

    # Update default_model
    code = code.replace(
        'self.default_model = default_model or "meta-llama/llama-3.3-70b-instruct"',
        'self.default_model = default_model or "deepseek/deepseek-chat"'
    )

    # Enhance system prompt
    old_sys_prompt = '''                    "You are an expert in viral video editing and short-form content creation (TikTok, YouTube Shorts, Reels). "
                    "Analyze the transcript and identify 3 to 7 of the most engaging, high-impact moments. "
                    "Focus on strong hooks, emotional moments, surprising insights, and punchy conclusions. "
                    "CRITICAL: Timestamps MUST use 'MM:SS' format (e.g. '01:30' for 1 minute 30 seconds). "
                    "CRITICAL: Each clip must be between 30 and 90 seconds long (end_time - start_time >= 30s, up to 120s for complete thoughts). "
                    "CRITICAL: start_time MUST be strictly less than end_time, and NEVER the same value. "
                    "Return ONLY valid JSON matching the requested schema. No markdown formatting, preamble or explanation."'''

    new_sys_prompt = '''                    "You are an elite short-form video editor specialized in viral TikToks, YouTube Shorts, and Instagram Reels. "
                    "Your mission is to extract the 3 to 7 highest-impact, most viral segments from this podcast transcript.\\n\\n"
                    "RULES FOR VIRAL RETENTION:\\n"
                    "1. VIRAL HOOK (First 3 seconds): Must start with immediate tension, a shocking confession, provocative question, or curiosity gap. Never start on filler words ('então', 'tipo assim').\\n"
                    "2. SELF-CONTAINED NARRATIVE: The viewer must understand the entire point/joke without needing context from 20 minutes earlier.\\n"
                    "3. CLIMAX & CLEAN ENDING: End on an emotional peak, burst of laughter, punchline, or powerful life lesson. Never cut mid-sentence.\\n"
                    "4. STRICT ANTI-SPONSOR & ANTI-INTRO FILTER: Strictly SKIP opening minutes containing greetings/sound checks, sponsor readings, discount codes ('cupom', 'patrocínio', 'merchan', 'link na descrição', 'superchat', 'manda o pix').\\n"
                    "5. OPTIMAL DURATION: 30 to 70 seconds (the algorithmic sweet spot for >100% completion rate).\\n"
                    "6. TIMESTAMPS: Strictly valid 'MM:SS' format found in transcript. start_time MUST be strictly less than end_time.\\n\\n"
                    "Return ONLY valid JSON matching the requested schema. No markdown, no backticks, no preamble."'''

    if old_sys_prompt in code:
        code = code.replace(old_sys_prompt, new_sys_prompt)
        print("Updated System Prompt with Anti-Jabá and Viral Hook rules")

    # Enhance _build_analysis_prompt
    old_prompt_builder = '''        return f"""Analyze the video transcript below and find the 3 to 7 best segments for viral short clips:

VIDEO METADATA:
- Duration: {duration_s:.0f} seconds ({duration_str} in MM:SS)
- Title: {metadata.get('title', 'N/A')}

CRITICAL TIMESTAMP RULES:
1. All start_time and end_time values MUST be valid MM:SS strings found within the transcript.
2. start_time MUST be less than end_time.
3. Each clip duration must be between 30 and 90 seconds long (can extend up to 120 seconds if needed for a complete thought).
4. Never use the same start and end timestamp.

TRANSCRIPT WITH TIMESTAMPS:
{transcript}

RESPONSE FORMAT (JSON only, no markdown, no other text):'''

    new_prompt_builder = '''        return f"""Analyze the podcast transcript below and identify the 3 to 7 most viral, high-retention segments:

VIDEO METADATA:
- Duration: {duration_s:.0f} seconds ({duration_str} in MM:SS)
- Title: {metadata.get('title', 'N/A')}

CRITICAL VIRALITY RULES:
1. Strictly avoid the introductory minutes if they contain generic greetings, technical sound tests, or reading sponsors.
2. Completely discard segments mentioning promotions, coupon codes, channel subscriptions or social media plugs.
3. Prioritize moments of high emotion: intense storytelling, revelations, conflict, humor, and counter-intuitive insights.
4. Timestamps MUST be MM:SS format matching the transcript timestamps.

TRANSCRIPT WITH TIMESTAMPS:
{transcript}

RESPONSE FORMAT (JSON only, no markdown, no other text):'''

    if old_prompt_builder in code:
        code = code.replace(old_prompt_builder, new_prompt_builder)
        print("Updated Analysis Prompt Builder")

    llm_service_path.write_text(code, encoding="utf-8")
    print("Successfully saved openrouter_llm.py")
