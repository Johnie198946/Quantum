import React from 'react';
import LiquidNav from './LiquidNav';
const icons=['calendar','sliders','leaf'];
export default function RequirementSteps({sections,step,onStep}){
 return <LiquidNav items={sections.map(([title],i)=>[i,title,icons[i]])} value={step} onChange={onStep} label="旅行需求步骤" labelPrefix="编辑" step className="requirement-steps liquid-requirement-steps"/>;
}
