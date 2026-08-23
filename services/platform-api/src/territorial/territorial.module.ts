import {Module} from '@nestjs/common';
import {TerritorialController} from './territorial.controller';
import {TerritorialService} from './territorial.service';

@Module({controllers:[TerritorialController],providers:[TerritorialService],exports:[TerritorialService]})
export class TerritorialModule{}
