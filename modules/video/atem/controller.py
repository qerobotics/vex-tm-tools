import PyATEMMax
import logging

logger = logging.getLogger(__name__)

class AtemController:
    def __init__(self, atem_ip):
        self.atem_ip = atem_ip
        self.atem = PyATEMMax.ATEMMax()
        self._connect()

    def _connect(self):
        try:
            logger.info(f"Connecting to ATEM switcher at {self.atem_ip}...")
            self.atem.connect(self.atem_ip)
            self.atem.waitForConnection(timeout=5)
            if self.atem.connected:
                logger.info("Successfully connected to ATEM switcher.")
            else:
                logger.error("Failed to connect to ATEM switcher.")
        except Exception as e:
            logger.error(f"Error connecting to ATEM: {e}")

    def _ensure_connection(self):
        if not self.atem.connected:
            logger.warning("ATEM not connected. Attempting to reconnect...")
            self._connect()
        return self.atem.connected

    def execute_action(self, action):
        if not self._ensure_connection():
            logger.error("Cannot execute ATEM action, no connection.")
            return

        camera_id = action.camera_id
        logger.info(f"Executing ATEM action: Switch to camera {camera_id}")

        try:
            # In PyATEMMax, camera IDs are usually integers.
            # We assume the camera_id in the action maps to a Program Input index.
            cam_index = int(camera_id)
            self.atem.changeProgramInput(cam_index)
            logger.info(f"Switched program input to {cam_index}")
        except ValueError:
            logger.error(f"Invalid camera_id for ATEM: {camera_id}. Must be an integer.")
        except Exception as e:
            logger.error(f"An unexpected error occurred during ATEM action: {e}")

    def disconnect(self):
        if self.atem.connected:
            logger.info("Disconnecting from ATEM switcher.")
            self.atem.disconnect()

if __name__ == '__main__':
    # Example usage for testing
    import os
    from models.actions import VideoAction
    import time

    ATEM_IP = os.environ.get("ATEM_IP")

    if not ATEM_IP:
        print("Please set the ATEM_IP environment variable.")
    else:
        logging.basicConfig(level=logging.INFO)
        atem_controller = AtemController(ATEM_IP)

        if atem_controller.atem.connected:
            print("ATEM controller initialized.")
            
            # Example: Switch to camera 1 (Program Input 1)
            action1 = VideoAction(camera_id=1)
            atem_controller.execute_action(action1)
            
            time.sleep(3)
            
            # Example: Switch to camera 2 (Program Input 2)
            action2 = VideoAction(camera_id=2)
            atem_controller.execute_action(action2)

            atem_controller.disconnect()
