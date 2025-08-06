/**
 * Event queue system for deterministic animations
 */

export interface ScheduledEvent {
  id: string;
  callback: () => void;
  resolved?: boolean;
  error?: Error; // If the event caused an error, store it here.
}

export class EventQueue {
  private events: ScheduledEvent[] = [];
  private startTime: number = 0;
  private isRunning: boolean = false;

  /**
   * Start the event queue with current time as reference
   */
  start(): void {
    this.isRunning = true;
  }

  /**
   * Stop the event queue
   */
  stop(): void {
    this.isRunning = false;
  }

  /**
   * Reset the event queue, clearing all events
   * @param resetCallback Optional callback to run after reset (for cleanup)
   */
  reset(resetCallback?: () => void): void {
    this.events = [];
    this.isRunning = false;
    if (resetCallback) {
      resetCallback();
    }
  }

  /**
   * Add an event to the queue
   */
  schedule(event: ScheduledEvent): void {
    this.events.push(event);
  }


  /**
   * Update the event queue, triggering events that are ready
   */
  update(): void {
    if (!this.isRunning) return;
    if (this.events.length < 1) return;

    if (this.events[0].resolved) {
      this.events.shift()
      this.events[0].callback()
    }
  }

  /**
   * Get remaining events count
   */
  get pendingCount(): number {
    return this.events.filter(e => !e.resolved).length;
  }

  /**
   * Get all events (for debugging)
   */
  get allEvents(): ScheduledEvent[] {
    return [...this.events];
  }
}
