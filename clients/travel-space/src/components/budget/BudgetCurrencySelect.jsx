import React from 'react';
import AlignedSelect from '../AlignedSelect';
import {currencies} from '../CurrencyPicker';

const options=currencies.map(([code,,name])=>[code,name+' · '+code]);

export default function BudgetCurrencySelect({value,onChange,label='结算币种',compact=false}){
 return <div className={'budget-currency-select'+(compact?' is-summary':'')}><AlignedSelect label={label} value={value} options={options} onChange={onChange}/></div>;
}
