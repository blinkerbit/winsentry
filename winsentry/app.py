"""FastAPI application factory for WinSentry"""

import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .database import DatabaseManager
from .log_manager import LogManager, MonitoringLogger
from .script_executor import ScriptExecutor
from .alert_engine import AlertEngine
from .monitors import PortMonitor, ProcessMonitor, ServiceMonitor, SystemMonitor
from .background_monitor import BackgroundMonitor
from .supervisor import ProcessSupervisor


def create_app(db: DatabaseManager, log_dir: str, workers: int = 4) -> FastAPI:
    """
    Create and configure the FastAPI application
    
    Args:
        db: Database manager instance
        log_dir: Directory for log files
        workers: Number of script execution workers
    
    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="WinSentry",
        description="Windows System Monitoring & Alerting Tool",
        version=__version__
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Allow all origins for local access
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Initialize global components
    from . import log_manager as log_manager_module
    from . import script_executor as script_executor_module
    from . import alert_engine as alert_engine_module
    
    log_manager_module.log_manager = LogManager(os.path.join(log_dir, "script_execution"))
    log_manager_module.monitoring_logger = MonitoringLogger(os.path.join(log_dir, "monitoring"))
    script_executor_module.script_executor = ScriptExecutor(
        max_workers=workers,
        log_manager=log_manager_module.log_manager
    )
    alert_engine_module.alert_engine = AlertEngine(db)
    
    # Store in app state for access in endpoints
    app.state.db = db
    app.state.log_manager = log_manager_module.log_manager
    app.state.monitoring_logger = log_manager_module.monitoring_logger
    app.state.script_executor = script_executor_module.script_executor
    app.state.alert_engine = alert_engine_module.alert_engine
    
    # Initialize monitors
    app.state.port_monitor = PortMonitor()
    app.state.process_monitor = ProcessMonitor()
    app.state.service_monitor = ServiceMonitor()
    app.state.system_monitor = SystemMonitor()
    
    # Initialize background monitoring service
    app.state.background_monitor = BackgroundMonitor(
        db=db,
        port_monitor=app.state.port_monitor,
        process_monitor=app.state.process_monitor,
        service_monitor=app.state.service_monitor,
        system_monitor=app.state.system_monitor,
        script_executor=script_executor_module.script_executor,
        monitoring_logger=log_manager_module.monitoring_logger,
        alert_engine=alert_engine_module.alert_engine
    )
    
    # Initialize process supervisor
    app.state.supervisor = ProcessSupervisor(
        db=db,
        monitoring_logger=log_manager_module.monitoring_logger
    )
    
    # Register API routes
    from .api import router
    app.include_router(router, prefix="/api")
    
    # Mount static files for frontend (serve at root)
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
    
    @app.on_event("startup")
    async def startup_event():
        """Initialize on startup"""
        print(f"✅ WinSentry {__version__} initialized")
        print(f"📊 Database: {db.db_path}")
        print(f"⚙️  Script workers: {workers}")
        
        # Start recurring alerts
        app.state.alert_engine.start_recurring_alerts()
        
        # Start background monitoring
        app.state.background_monitor.start()
        
        # Start process supervisor
        app.state.supervisor.start()
    
    @app.on_event("shutdown")
    async def shutdown_event():
        """Cleanup on shutdown"""
        print("🛑 Shutting down WinSentry...")
        
        # Stop background monitoring
        if app.state.background_monitor:
            app.state.background_monitor.stop()
        
        # Stop process supervisor
        if app.state.supervisor:
            app.state.supervisor.stop()
        
        # Stop script executor
        if app.state.script_executor:
            app.state.script_executor.stop()
        
        # Stop alert engine
        if app.state.alert_engine:
            app.state.alert_engine.stop()
    
    return app

