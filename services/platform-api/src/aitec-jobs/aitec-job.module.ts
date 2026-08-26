import {Module} from '@nestjs/common';
import {CoreModule} from '../core.module';
import {AitecJobController} from './aitec-job.controller';

@Module({imports:[CoreModule],controllers:[AitecJobController]})
export class AitecJobModule{}
