import os, time, importlib.util
from autonomous_engine import AutonomousEngine

# Load the existing renderer without starting its old background worker.
os.environ['GTA_AUTONOMOUS_DISABLE_LEGACY_WORKER']='1'
spec=importlib.util.spec_from_file_location('legacy_app','app_legacy_V41.py')
legacy=importlib.util.module_from_spec(spec); spec.loader.exec_module(legacy)
engine=AutonomousEngine(legacy)

if __name__=='__main__':
    engine.loop()
