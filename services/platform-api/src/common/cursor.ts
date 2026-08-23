export type CursorPayload={createdAt:string;id:string};

export function encodeCursor(value:CursorPayload){
  return Buffer.from(JSON.stringify(value),'utf8').toString('base64url');
}

export function decodeCursor(value?:string|null):CursorPayload|null{
  if(!value)return null;
  try{
    const parsed=JSON.parse(Buffer.from(value,'base64url').toString('utf8'));
    if(typeof parsed?.createdAt!=='string'||typeof parsed?.id!=='string')return null;
    return parsed;
  }catch{return null;}
}

export function pageLimit(raw?:string|number|null,defaultValue=50,max=200){
  const n=Number(raw??defaultValue);
  if(!Number.isInteger(n)||n<1)return defaultValue;
  return Math.min(n,max);
}
