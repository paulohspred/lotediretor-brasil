import {Module} from '@nestjs/common';
import {CoreModule} from '../core.module';
import {TerritorialController} from './territorial.controller';
import {TerritorialService} from './territorial.service';

@Module({imports:[CoreModule],controllers:[TerritorialController],providers:[TerritorialService],exports:[TerritorialService]})
export class TerritorialModule{}
