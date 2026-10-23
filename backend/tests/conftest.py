import os

# Tests must not pick up a developer's backend/.env (env vars beat the env file): a configured
# Colab worker would otherwise receive real jobs and make the suite depend on a live tunnel.
os.environ["GPU_WORKER_MODE"] = "off"
os.environ["GPU_WORKER_URL"] = ""
os.environ["GPU_WORKER_TOKEN"] = ""
