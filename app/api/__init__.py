"""FastAPI routers. The parse/annotate routers import only local core modules —
never a network client — so the runtime path cannot make outbound connections.
"""
