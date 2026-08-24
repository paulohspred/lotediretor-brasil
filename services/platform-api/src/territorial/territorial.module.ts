import {Module} from '@nestjs/common';
import {TerritorialController} from './territorial.controller';
import {TerritorialService} from './territorial.service';
import {AnalysisV20Service} from './analysis-v20.service';

@Module({controllers:[TerritorialController],providers:[TerritorialService,AnalysisV20Service],exports:[TerritorialService,AnalysisV20Service]})
export class TerritorialModule{}
