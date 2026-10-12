import React from 'react';
import { useReducedMotion } from 'motion/react';
import { ThinkingOrb } from 'thinking-orbs';

// A single visual tuning for all travel thinking and its inward/outward motions.
export default function TravelThinkingOrb({size=64}) {
  const reduced=useReducedMotion();
  return <span className="travel-thinking-orb" aria-hidden="true" data-orb-state="weaving" data-orb-size={size} style={{width:size,height:size}}>
    <ThinkingOrb state="weaving" size={size} theme="light" color="#607264" speed={1.1} paused={!!reduced}/>
  </span>;
}
