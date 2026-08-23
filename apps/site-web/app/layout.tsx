import type {ReactNode} from 'react';import '@lotediretor/design-tokens/tokens.css';
import '@lotediretor/ui/ui.css';
import './site.css';
export const metadata={title:'LoteDiretor Brasil',description:'Inteligência urbanística, territorial e imobiliária.'};
export default function RootLayout({children}:{children:ReactNode}){return <html lang="pt-BR"><body>{children}</body></html>}
