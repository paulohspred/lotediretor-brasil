import {Module} from '@nestjs/common';
import {PrivacyV20Controller} from './privacy-v20.controller';

@Module({controllers:[PrivacyV20Controller]})
export class PrivacyModule{}
