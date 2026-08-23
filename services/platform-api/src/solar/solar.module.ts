import {Module} from '@nestjs/common';
import {CoreModule} from '../core.module';
import {SolarController} from './solar.controller';
@Module({imports:[CoreModule],controllers:[SolarController]})
export class SolarModule{}
