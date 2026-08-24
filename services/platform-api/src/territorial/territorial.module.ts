import {Module} from '@nestjs/common';
import {CoreModule} from '../core.module';
import {TerritorialController} from './territorial.controller';
import {TerritorialService} from './territorial.service';
import {AnalysisV20Service} from './analysis-v20.service';

@Module({
  imports:[CoreModule],
  controllers:[TerritorialController],
  providers:[TerritorialService,AnalysisV20Service],
  exports:[TerritorialService,AnalysisV20Service],
})
export class TerritorialModule{}
