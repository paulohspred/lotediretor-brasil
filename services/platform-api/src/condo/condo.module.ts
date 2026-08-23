import {Module} from '@nestjs/common';
import {CoreModule} from '../core.module';
import {CondoController} from './condo.controller';
@Module({imports:[CoreModule],controllers:[CondoController]})
export class CondoModule{}
