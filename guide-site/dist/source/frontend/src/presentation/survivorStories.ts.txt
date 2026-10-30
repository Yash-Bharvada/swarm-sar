/** Fictional dialogue, deterministic without consuming the mission RNG. */
const STORIES = [
  'My daughter is somewhere out there. Please find her. She owes me a hug, and an explanation for teaching me to use airplane mode.',
  'Thank goodness you found me! I was about to leave a one-star review for this escape room.',
  'Any chance the next rover carries snacks? I am incredibly hungry. I could eat a whole picnic.',
  'I have been here for a decade! Okay, maybe an hour. Time gets very strange when your phone dies.',
  'I was following the emergency exit signs. Turns out my sense of direction needs an upgrade.',
  'Please tell whoever built you that your little wheels have just made my entire day.',
  'I kept tapping on the wall. Thanks for listening. My rhythm is terrible, so please do not upload the recording.',
  'I promised I would be home for dinner. If anyone asks, this was a very ambitious shortcut.',
  'Can I name that drone Biscuit? It looks like a Biscuit. A very heroic Biscuit.',
  'My cat is going to be furious that dinner is late. I am going to blame the maze.',
  'I was saving my last battery bar for a rescue call. You beat my phone to it!',
  'When this is over, I owe your whole swarm a thank-you card. Do robots prefer stickers?',
  'You have thermal vision and I still cannot find my glasses. Could we put that on the agenda?',
  'I tried asking the wall for directions. Excellent listener. Terrible navigator.',
  'Please tell me the rescue package includes tea. I have already supplied the dramatic backstory.',
  'Is that a rover or a tiny snack delivery service? Please say both.',
  'I knew help would come. I just imagined a slightly taller rescue team.',
  'My smartwatch says I need more steps. I would like to formally disagree.',
  'I have named all the bricks. Gerald over there has been very supportive.',
  'I was being very brave until my stomach growled and scared me.',
  'Does your drone take passengers? Asking for me, my knees, and my complete lack of enthusiasm for walking.',
  'You found me faster than my friends find the restaurant we agreed on.',
  'I would shake your hand, but you appear to be four wheels and excellent intentions.',
  'Before we go: did anyone rescue my lunch? We have been through a lot together.',
];
const NAMES = ['Maya', 'Arun', 'Sam', 'Leah', 'Noor', 'Theo', 'Isha', 'Alex', 'Riya', 'Omar', 'June', 'Kai'];

export function survivorStory(seed: number, id: number) {
  const mixed = (Math.imul(seed | 0, 1664525) + 1013904223) >>> 0;
  return { name: NAMES[(mixed + id) % NAMES.length], text: STORIES[(mixed + id) % STORIES.length] };
}

/** High contrast mint = sensed; warm, muted ground = not yet sensed. */
export function coverageColor(known: boolean): [number, number, number, number] {
  return known ? [44, 151, 129, 122] : [158, 119, 66, 48];
}
