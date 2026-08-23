import {Module} from '@nestjs/common';
import {PlatformMetricsController} from './v8.metrics.controller';

@Module({controllers:[PlatformMetricsController]})
export class MetricsModule{}
