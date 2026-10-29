/** Fictional dialogue, deterministic without consuming the mission RNG. */
const STORIES = [
  'My daughter is somewhere out there. Please keep looking for her. Your little team gives me hope.',
  'Thank goodness this swarm found me! I never thought the sound of tiny rotors could feel so reassuring.',
  'Any chance the next rover carries snacks? I am incredibly hungry. I could eat a whole picnic.',
  'I have been here for a decade! Okay, maybe an hour. Time gets very strange when your phone dies.',
  'I was following the emergency exit signs. Turns out my sense of direction needs an upgrade.',
  'Please tell whoever built you that your little wheels have just made my entire day.',
  'I kept tapping on the wall and hoping someone would hear. You actually listened. Thank you.',
  'I promised my family I would be home for dinner. Let us make sure everyone else gets home too.',
  'Can I name that drone Biscuit? It looks like a Biscuit. A very heroic Biscuit.',
  'My cat is going to be furious that dinner is late. I am going to blame the maze.',
  'I was saving my last battery bar for a rescue call. You beat my phone to it!',
  'When this is over, I owe your whole swarm a thank-you card. Do robots prefer stickers?',
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
