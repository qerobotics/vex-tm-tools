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
            logger.debug(f"ATEM connection attempt started for IP: {self.atem_ip}")
            self.atem.connect(self.atem_ip)
            self.atem.waitForConnection(timeout=5)
            if self.atem.connected:
                logger.info("Successfully connected to ATEM switcher.")
                logger.debug(f"ATEM connection status: connected={self.atem.connected}")
            else:
                logger.error("Failed to connect to ATEM switcher.")
                logger.debug(f"ATEM connection failed - connected status: {self.atem.connected}")
        except Exception as e:
            logger.error(f"Error connecting to ATEM: {e}")
            logger.debug(f"ATEM connection exception details: {e}", exc_info=True)

    def _ensure_connection(self):
        logger.debug(f"Checking ATEM connection status: connected={self.atem.connected}")
        if not self.atem.connected:
            logger.warning("ATEM not connected. Attempting to reconnect...")
            self._connect()
        logger.debug(f"ATEM connection check result: {self.atem.connected}")
        return self.atem.connected

    def execute_action(self, action):
        logger.debug(f"ATEM execute_action called with action: {action}")
        logger.debug(f"Action type: {type(action)}, camera_id: {getattr(action, 'camera_id', None)}, command: {getattr(action, 'command', None)}")
        
        if not self._ensure_connection():
            logger.error("Cannot execute ATEM action, no connection.")
            logger.debug(f"ATEM connection failed, connected={self.atem.connected}")
            return

        command = action.command
        logger.debug(f"Processing ATEM command: {command}")
        
        # Handle fade to black
        if command == "fade_to_black":
            logger.info("Executing ATEM fade to black")
            logger.debug("Triggering fade to black on ME1")
            try:
                # Perform fade to black on ME1 (index 0)
                self.atem.performFadeToBlackME(0)
                logger.info("Fade to black triggered on ME1")
                logger.debug("ATEM performFadeToBlackME(0) command sent successfully")
            except Exception as e:
                logger.error(f"Error triggering fade to black: {e}")
                logger.debug(f"Exception details during fade to black", exc_info=True)
            return

        # Handle program input change (camera switching)
        camera_id = action.camera_id
        if not camera_id:
            logger.error("No camera_id provided for ATEM action")
            logger.debug(f"Action object: {action}, attributes: {vars(action)}")
            return
            
        logger.info(f"Executing ATEM action: Switch to camera {camera_id}")
        logger.debug(f"ATEM switcher ready, attempting to change program input to {camera_id}")

        try:
            # In PyATEMMax, camera IDs are usually integers.
            # We assume the camera_id in the action maps to a Program Input index.
            cam_index = int(camera_id)
            logger.debug(f"Converted camera_id '{camera_id}' to integer: {cam_index}")
            
            # Use the correct PyATEMMax method: setProgramInputVideoSource(mE, videoSource)
            # mE is the Mix Effect (0 for ME1, 1 for ME2, etc.)
            # For most setups, we'll use Mix Effect 1 (index 0)
            self.atem.setProgramInputVideoSource(0, cam_index)
            logger.info(f"Switched program input to {cam_index} on ME1")
            logger.debug(f"ATEM setProgramInputVideoSource(0, {cam_index}) command sent successfully")
        except ValueError:
            logger.error(f"Invalid camera_id for ATEM: {camera_id}. Must be an integer.")
            logger.debug(f"ValueError converting camera_id: {camera_id}", exc_info=True)
        except Exception as e:
            logger.error(f"An unexpected error occurred during ATEM action: {e}")
            logger.debug(f"Exception details during ATEM action", exc_info=True)

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
            action1 = VideoAction(command="switch", camera_id="1")
            atem_controller.execute_action(action1)
            
            time.sleep(3)
            
            # Example: Switch to camera 2 (Program Input 2)
            action2 = VideoAction(command="switch", camera_id="2")
            atem_controller.execute_action(action2)

            atem_controller.disconnect()
