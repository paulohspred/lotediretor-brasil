import {Module} from '@nestjs/common';
import {CoreModule} from './core.module';
import {V7Controller} from './v7.controller';

/**
 * Transitional domain module. v19-rc2 keeps the recovered domain surface behind
 * an explicit Nest module boundary. v19+ will split this controller by bounded
 * context without changing external contracts.
 */
@Module({imports:[CoreModule],controllers:[V7Controller]})
export class DomainsModule{}
