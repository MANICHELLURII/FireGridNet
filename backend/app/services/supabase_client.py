from functools import lru_cache

from supabase import create_client, Client

from app.config import settings


@lru_cache
def get_supabase() -> Client:
    """
    Cached Supabase client using the service-role key.
    Backend-only — never expose the service-role key to the frontend.
    """
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
