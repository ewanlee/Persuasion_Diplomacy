#!/bin/bash

python3 lm_game.py \
    --max_year 1901 \
    --num_negotiation_rounds 0 \
    --models "openrouter-google/gemini-2.5-flash-preview-05-20, openrouter-google/gemini-2.5-flash-preview-05-20, openrouter-google/gemini-2.5-flash-preview-05-20, openrouter-google/gemini-2.5-flash-preview-05-20, openrouter-google/gemini-2.5-flash-preview-05-20, openrouter-google/gemini-2.5-flash-preview-05-20, openrouter-google/gemini-2.5-flash-preview-05-20" \
    --max_tokens_per_model 16000,16000,16000,16000,16000,16000,16000