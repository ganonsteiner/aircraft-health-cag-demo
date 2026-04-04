import type { DemoMode } from "./store";

export const SUGGESTIONS: Record<DemoMode, string[]> = {
  clean: [
    "Is N4798E airworthy for today's flight?",
    "What maintenance is coming up in the next 50 hours?",
    "Tell me about the Flagstaff flights",
    "What does the POH say about density altitude?",
    "Has this aircraft complied with all ADs?",
    "Show me the engine health history",
  ],
  caution: [
    "What is the current airworthiness status?",
    "How overdue is the oil change?",
    "Is it safe to fly with a slightly overdue oil change?",
    "What should the owner do before the next flight?",
    "When is the annual due?",
    "What are the risks of a slightly overdue oil change?",
  ],
  grounded: [
    "Why is N4798E grounded?",
    "What are all the issues preventing flight?",
    "How serious is the rocker cover squawk?",
    "What needs to be fixed and in what order?",
    "What are the risks of the current squawk?",
    "How long would it take to return this aircraft to airworthy status?",
  ],
};
