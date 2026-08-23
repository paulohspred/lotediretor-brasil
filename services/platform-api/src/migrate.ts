import {join} from 'path';
import {runMigrations} from './migrations';

const url=process.env.PLATFORM_MIGRATION_DATABASE_URL||'';
if(!url)throw new Error('PLATFORM_MIGRATION_DATABASE_URL is required');
runMigrations(url,join(process.cwd(),'db/platform/migrations')).then(()=>{console.log('platform migrations complete');process.exit(0)}).catch(e=>{console.error(e);process.exit(1)});
