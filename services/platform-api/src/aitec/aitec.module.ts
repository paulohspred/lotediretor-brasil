import {Module} from '@nestjs/common';
import {CoreModule} from '../core.module';
import {AitecJobsController} from './aitec-jobs.controller';

@Module({imports:[CoreModule],controllers:[AitecJobsController]})
export class AitecModule{}
