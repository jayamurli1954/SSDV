# Runtime hook: Streamlit must not run in development / file-watch mode when frozen.
import os

os.environ.setdefault("STREAMLIT_GLOBAL_DEVELOPMENT_MODE", "false")
os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
os.environ.setdefault("STREAMLIT_SERVER_FILE_WATCHER_TYPE", "none")
