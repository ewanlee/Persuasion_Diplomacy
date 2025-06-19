import { gameState } from "./gameState";
import { getPowerDisplayName } from './utils/powerNames';
import { PowerENUM } from './types/map';

class Logger {
  get infoPanel() {
    let _panel = document.getElementById('info-panel');
    if (_panel === null) {
      throw new Error("Unable to find the element with id 'info-panel'")
    }
    return _panel
  }

  // Modified to only log to console without updating the info panel
  log = (msg: string) => {
    if (typeof msg !== "string") {
      throw new Error(`Logger messages must be strings, you passed a ${typeof msg}`);
    }
    // Remove the update to infoPanel.textContent
    console.log(msg);
  }

}
export const logger = new Logger()
