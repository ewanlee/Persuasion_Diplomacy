/**
 * Event queue system for deterministic animations
 */

import { config } from "./config";
import { debugMenuInstance } from "./debug/debugMenu";
import { toggleEventQueueDisplayState } from "./debug/eventQueueDisplay";
import { debugMenu } from "./domElements";

export class ScheduledEvent {
  id: string;
  callback: () => void;
  resolved?: boolean;
  running!: boolean;
  error?: Error; // If the event caused an error, store it here.
  constructor(id: string, callback: () => void, resolved?: boolean) {
    this.id = id
    this.callback = callback
    this.resolved = resolved ? true : resolved
  }
  run = () => {
    this.running = true
    try {
      this.callback();
    } catch (e) {
      this.error = e
    } finally {

      this.resolved = true
    }
  }
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
    this.events[0].run()
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
    if (!event || !(event instanceof ScheduledEvent)) {
      throw new Error("Attempted to schedule an invalid event")
    }
    this.events.push(event);
  }
  scheduleMany(events: ScheduledEvent[]): void {
    for (let event of events) {
      this.schedule(event)
    }
  }


  /**
   * Update the event queue, triggering events that are ready
   */
  update(): void {
    if (!this.isRunning) return;
    if (this.events.length < 1) return;

    if (this.events[0].resolved) {
      if (this.events[0].error) {
        console.error(this.events[0].error)
      }
      if (config.isDebugMode) {
        debugMenuInstance.updateTools()
      }
      this.events.shift()
      this.events[0].run()
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
