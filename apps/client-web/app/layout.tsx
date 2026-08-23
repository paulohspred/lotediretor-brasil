import type {ReactNode} from 'react';import '@lotediretor/design-tokens/tokens.css';import '@lotediretor/ui/ui.css';import 'maplibre-gl/dist/maplibre-gl.css';import './client.css';
export const metadata={title:'LoteDiretor | Plataforma'};
export default function Layout({children}:{children:ReactNode}){return <html lang="pt-BR"><body>{children}</body></html>}
