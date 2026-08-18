#import <CoreGraphics/CoreGraphics.h>
#import <Foundation/Foundation.h>
#import <ImageIO/ImageIO.h>
#import <Vision/Vision.h>

static void Fail(NSString *message) {
    fprintf(stderr, "%s\n", message.UTF8String);
    exit(2);
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc != 4) {
            Fail(@"Usage: subtitle_ocr <manifest.json> <output.json> <fast|accurate>");
        }

        NSString *manifestPath = [NSString stringWithUTF8String:argv[1]];
        NSString *outputPath = [NSString stringWithUTF8String:argv[2]];
        NSString *level = [NSString stringWithUTF8String:argv[3]];
        NSData *manifestData = [NSData dataWithContentsOfFile:manifestPath];
        if (manifestData == nil) {
            Fail(@"Unable to read OCR manifest.");
        }
        NSError *jsonError = nil;
        NSArray *items = [NSJSONSerialization JSONObjectWithData:manifestData
                                                         options:0
                                                           error:&jsonError];
        if (![items isKindOfClass:[NSArray class]]) {
            Fail([NSString stringWithFormat:@"Unable to decode OCR manifest: %@",
                                            jsonError.localizedDescription]);
        }

        NSMutableArray *output = [NSMutableArray arrayWithCapacity:items.count];
        for (NSDictionary *item in items) {
            NSString *path = [item[@"path"] description];
            NSNumber *timestamp = item[@"timestamp"] ?: @0;
            NSURL *url = [NSURL fileURLWithPath:path];
            CGImageSourceRef source = CGImageSourceCreateWithURL(
                (__bridge CFURLRef)url, NULL
            );
            CGImageRef image = source == NULL
                ? NULL
                : CGImageSourceCreateImageAtIndex(source, 0, NULL);
            if (source != NULL) {
                CFRelease(source);
            }
            if (image == NULL) {
                [output addObject:@{
                    @"path": path,
                    @"timestamp": timestamp,
                    @"lines": @[],
                    @"error": @"Unable to decode image",
                }];
                continue;
            }

            VNRecognizeTextRequest *request = [[VNRecognizeTextRequest alloc] init];
            request.recognitionLevel = [level isEqualToString:@"fast"]
                ? VNRequestTextRecognitionLevelFast
                : VNRequestTextRecognitionLevelAccurate;
            request.recognitionLanguages = @[@"zh-Hans", @"en-US"];
            request.usesLanguageCorrection = ![level isEqualToString:@"fast"];
            request.minimumTextHeight = 0.018;

            VNImageRequestHandler *handler = [
                [VNImageRequestHandler alloc] initWithCGImage:image options:@{}
            ];
            NSError *requestError = nil;
            BOOL succeeded = [handler performRequests:@[request] error:&requestError];
            CGImageRelease(image);
            if (!succeeded) {
                [output addObject:@{
                    @"path": path,
                    @"timestamp": timestamp,
                    @"lines": @[],
                    @"error": requestError.localizedDescription ?: @"OCR failed",
                }];
                continue;
            }

            NSArray<VNRecognizedTextObservation *> *observations = [
                (request.results ?: @[]) sortedArrayUsingComparator:
                    ^NSComparisonResult(
                        VNRecognizedTextObservation *left,
                        VNRecognizedTextObservation *right
                    ) {
                        CGFloat delta = CGRectGetMidY(left.boundingBox)
                            - CGRectGetMidY(right.boundingBox);
                        if (fabs(delta) > 0.025) {
                            return delta > 0 ? NSOrderedAscending : NSOrderedDescending;
                        }
                        CGFloat xDelta = CGRectGetMinX(left.boundingBox)
                            - CGRectGetMinX(right.boundingBox);
                        if (xDelta < 0) {
                            return NSOrderedAscending;
                        }
                        if (xDelta > 0) {
                            return NSOrderedDescending;
                        }
                        return NSOrderedSame;
                    }
            ];
            NSMutableArray *lines = [NSMutableArray array];
            for (VNRecognizedTextObservation *observation in observations) {
                VNRecognizedText *candidate = [observation topCandidates:1].firstObject;
                if (candidate == nil) {
                    continue;
                }
                CGRect box = observation.boundingBox;
                [lines addObject:@{
                    @"text": candidate.string,
                    @"confidence": @(candidate.confidence),
                    @"x": @(CGRectGetMinX(box)),
                    @"y": @(CGRectGetMinY(box)),
                    @"width": @(CGRectGetWidth(box)),
                    @"height": @(CGRectGetHeight(box)),
                }];
            }
            [output addObject:@{
                @"path": path,
                @"timestamp": timestamp,
                @"lines": lines,
                @"error": [NSNull null],
            }];
        }

        NSData *encoded = [NSJSONSerialization dataWithJSONObject:output
                                                          options:NSJSONWritingPrettyPrinted
                                                            error:&jsonError];
        if (
            encoded == nil
            || ![encoded writeToFile:outputPath
                             options:NSDataWritingAtomic
                               error:&jsonError]
        ) {
            Fail([NSString stringWithFormat:@"Unable to write OCR output: %@",
                                            jsonError.localizedDescription]);
        }
    }
    return 0;
}
