import {Module} from '@nestjs/common';
import {CoreModule} from '../core.module';
import {Property360Controller} from './property360.controller';
import {Property360B2BV20Controller,Property360V20Controller} from './property360-v20.controller';
@Module({imports:[CoreModule],controllers:[Property360Controller,Property360V20Controller,Property360B2BV20Controller]})
export class Property360Module{}
