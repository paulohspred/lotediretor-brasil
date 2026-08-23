import {Module} from '@nestjs/common';
import {CoreModule} from '../core.module';
import {ReportController} from './report.controller';
@Module({imports:[CoreModule],controllers:[ReportController]})
export class ReportModule{}
