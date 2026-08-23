import type {ReactNode} from 'react';import React from 'react';
export function Button({children, variant='primary', ...props}:{children:ReactNode;variant?:'primary'|'secondary'|'danger'} & React.ButtonHTMLAttributes<HTMLButtonElement>){
  return <button className={`ld-btn ld-btn--${variant}`} {...props}>{children}</button>;
}
export function Card({children,className=''}:{children:ReactNode;className?:string}){return <section className={`ld-card ${className}`}>{children}</section>}
export function Badge({children,tone='neutral'}:{children:ReactNode;tone?:'neutral'|'success'|'warning'|'danger'|'info'}){return <span className={`ld-badge ld-badge--${tone}`}>{children}</span>}
