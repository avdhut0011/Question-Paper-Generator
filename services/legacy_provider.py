"""Modern SDK adapter for the original QPG model interfaces."""
from flask import current_app, g


def configure(api_key=None):
    # Original modules call this at import time. Actual configuration is resolved
    # per application context instead of mutating a process-global SDK client.
    return None


class GenerativeModel:
    def __init__(self, model_name):
        self.model_name = model_name

    def generate_content(self, prompt):
        from google import genai
        from google.genai import types
        try:
            with genai.Client(api_key=current_app.config['GEMINI_API_KEY'],
                              http_options=types.HttpOptions(timeout=90000)) as client:
                response = client.models.generate_content(model=current_app.config['GEMINI_MODEL'] or self.model_name,
                    contents=prompt, config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=24000))
            usage = response.usage_metadata
            if not hasattr(g, 'qpg_usage'):
                g.qpg_usage = []
            g.qpg_usage.append({'input_tokens': getattr(usage, 'prompt_token_count', None),
                                'output_tokens': getattr(usage, 'candidates_token_count', None)})
            return response
        except Exception:
            raise ValueError('The AI service could not complete generation. Check the configured model and API access.') from None
