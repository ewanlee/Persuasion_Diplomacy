import { gameState } from "../gameState";
import { getPowerDisplayName } from "../utils/powerNames";
import { PowerENUM } from "../types/map";


let containerElement = document.getElementById("leaderboard")

export function initLeaderBoard() {
  if (!containerElement) {
    console.error(`Container element with ID "leaderboard" not found`);
    return;
  }
}


// Updated function to update leaderboard with useful information and smooth transitions
export function updateLeaderboard() {
  const totalPhases = gameState.gameData?.phases?.length || 0;
  const currentPhaseNumber = gameState.phaseIndex + 1;
  const phaseName = gameState.gameData?.phases?.[gameState.phaseIndex]?.name || 'Unknown';

  // Add fade-out transition
  containerElement.style.transition = 'opacity 0.3s ease-out';

  // Get supply center counts for the current phase
  const scCounts = getSupplyCenterCounts();

  containerElement.innerHTML = `
        <div><strong>Playing As:</strong> <span class="power-${gameState.currentPower.toLowerCase()}">${getPowerDisplayName(gameState.currentPower)}</span></div>
        <hr/>
        <h4>Supply Center Counts</h4>
        <ul style="list-style:none;padding-left:0;margin:0;">
          <li><span class="power-austria">${getPowerDisplayName(PowerENUM.AUSTRIA)}:</span> ${scCounts.AUSTRIA || 0}</li>
          <li><span class="power-england">${getPowerDisplayName(PowerENUM.ENGLAND)}:</span> ${scCounts.ENGLAND || 0}</li>
          <li><span class="power-france">${getPowerDisplayName(PowerENUM.FRANCE)}:</span> ${scCounts.FRANCE || 0}</li>
          <li><span class="power-germany">${getPowerDisplayName(PowerENUM.GERMANY)}:</span> ${scCounts.GERMANY || 0}</li>
          <li><span class="power-italy">${getPowerDisplayName(PowerENUM.ITALY)}:</span> ${scCounts.ITALY || 0}</li>
          <li><span class="power-russia">${getPowerDisplayName(PowerENUM.RUSSIA)}:</span> ${scCounts.RUSSIA || 0}</li>
          <li><span class="power-turkey">${getPowerDisplayName(PowerENUM.TURKEY)}:</span> ${scCounts.TURKEY || 0}</li>
        </ul>
      `;
}

// Helper function to count supply centers for each power
function getSupplyCenterCounts() {
  const counts = {
    AUSTRIA: 0,
    ENGLAND: 0,
    FRANCE: 0,
    GERMANY: 0,
    ITALY: 0,
    RUSSIA: 0,
    TURKEY: 0
  };

  // Get current phase's supply center data
  const centers = gameState.gameData?.phases?.[gameState.phaseIndex]?.state?.centers;

  if (centers) {
    // Count supply centers for each power
    Object.entries(centers).forEach(([power, provinces]) => {
      if (power && Array.isArray(provinces)) {
        counts[power as keyof typeof counts] = provinces.length;
      }
    });
  }

  return counts;
}
