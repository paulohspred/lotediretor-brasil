import {Module} from '@nestjs/common';
import {CoreModule} from '../core.module';
import {RuralController} from './rural.controller';
@Module({imports:[CoreModule],controllers:[RuralController]})
export class RuralModule{}
