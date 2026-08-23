import {Module} from '@nestjs/common';
import {CoreModule} from '../core.module';
import {Property360Controller} from './property360.controller';
@Module({imports:[CoreModule],controllers:[Property360Controller]})
export class Property360Module{}
