import {join} from 'path';
import {runMigrations} from './migrations';

const url=process.env.CONTROL_MIGRATION_DATABASE_URL||'';
if(!url)throw new Error('CONTROL_MIGRATION_DATABASE_URL is required');
runMigrations(url,join(process.cwd(),'db/control/migrations')).then(()=>{console.log('control migrations complete');process.exit(0)}).catch(e=>{console.error(e);process.exit(1)});
