import {Module} from '@nestjs/common';
import {CoreModule} from '../core.module';
import {MunicipalityV20Controller} from './municipality-v20.controller';
import {MunicipalityOpenDataV20Controller} from './municipality-open-v20.controller';
import {MunicipalityExportV20Controller} from './municipality-export-v20.controller';

@Module({imports:[CoreModule],controllers:[MunicipalityV20Controller,MunicipalityOpenDataV20Controller,MunicipalityExportV20Controller]})
export class MunicipalityModule{}
