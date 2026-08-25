import {Module} from '@nestjs/common';
import {CoreModule} from '../core.module';
import {CondoController} from './condo.controller';
import {CondoV20Controller} from './condo-v20.controller';
import {CondoV20OpsController} from './condo-v20-ops.controller';
@Module({imports:[CoreModule],controllers:[CondoController,CondoV20Controller,CondoV20OpsController]})
export class CondoModule{}
