#!/bin/bash

python3 lm_game.py \
    --max_year 1901 \
    --num_negotiation_rounds 1 \
    --models "openrouter-google/gemini-2.5-flash-lite-preview-06-17, openrouter-google/gemini-2.5-flash-lite-preview-06-17, openrouter-google/gemini-2.5-flash-lite-preview-06-17, openrouter-google/gemini-2.5-flash-lite-preview-06-17, openrouter-google/gemini-2.5-flash-lite-preview-06-17, openrouter-google/gemini-2.5-flash-lite-preview-06-17, openrouter-google/gemini-2.5-flash-lite-preview-06-17" \
    --max_tokens_per_model 16000,16000,16000,16000,16000,16000,16000 \
    --prompts_dir "ai_diplomacy/prompts"