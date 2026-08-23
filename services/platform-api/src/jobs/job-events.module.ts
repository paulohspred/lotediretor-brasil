import {Module} from '@nestjs/common';
import {CoreModule} from '../core.module';
import {JobEventsController} from './job-events.controller';

@Module({imports:[CoreModule],controllers:[JobEventsController]})
export class JobEventsModule{}
