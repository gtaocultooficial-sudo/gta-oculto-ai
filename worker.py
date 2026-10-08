import os
os.environ['GTA_AUTONOMOUS_DISABLE_LEGACY_WORKER']='1'

from autonomous_engine import AutonomousEngine
import app as legacy

engine = AutonomousEngine(legacy)

if __name__ == '__main__':
    engine.loop()
