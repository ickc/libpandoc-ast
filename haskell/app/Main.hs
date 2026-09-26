{-# LANGUAGE OverloadedStrings   #-}
{-# LANGUAGE TemplateHaskell     #-}
{- |
   Module      : Main
   Copyright   : Copyright (C) 2026 Kolen Cheung
   License     : BSD-3-Clause

Writes, from the pandoc-types this is built with:

- @reified.json@: pandoc's document types, as declared (see "SchemaTH");
- @arbitrary.jsonl@: random documents, one per line, encoded by pandoc-types'
  own aeson instances. They come from pandoc-types' QuickCheck generators,
  with fixed seeds, plus metadata of every kind (which those generators
  don't produce).

Every binding must decode and re-encode each document unchanged: that is
what keeps a binding's encoding identical to pandoc's.

    libpandoc-ast-schema OUTDIR [COUNT]
-}
module Main (main) where

import qualified Data.Aeson as Aeson
import qualified Data.ByteString.Char8 as B8
import qualified Data.ByteString.Lazy.Char8 as BL8
import qualified Data.Map as M
import qualified Data.Text as T
import System.Directory (createDirectoryIfMissing)
import System.Environment (getArgs)
import System.FilePath ((</>))
import Test.QuickCheck (Arbitrary (..), Gen, choose, elements, frequency,
                        listOf, resize, vectorOf)
import Test.QuickCheck.Gen (unGen)
import Test.QuickCheck.Random (mkQCGen)
import Text.Pandoc.Arbitrary ()
import Text.Pandoc.Definition

import SchemaTH (schemaOf)

main :: IO ()
main = do
  args <- getArgs
  (out, count) <- case args of
    [o] -> pure (o, 200)
    [o, n] -> pure (o, read n)
    _ -> fail "usage: libpandoc-ast-schema OUTDIR [COUNT]"
  createDirectoryIfMissing True out
  B8.writeFile (out </> "reified.json") (B8.pack $(schemaOf ''Pandoc) <> "\n")
  BL8.writeFile (out </> "arbitrary.jsonl") $ BL8.unlines
    [ Aeson.encode (unGen document (mkQCGen seed) 8) | seed <- [0 .. count - 1] ]

-- | pandoc-types' own generator, with metadata of every kind added.
document :: Gen Pandoc
document = do
  Pandoc (Meta meta) blocks <- arbitrary
  extra <- M.fromList <$> listOf ((,) <$> key <*> metaValue 2)
  pure (Pandoc (Meta (M.union meta extra)) blocks)

metaValue :: Int -> Gen MetaValue
metaValue n = frequency $
  [ (3, MetaString <$> text)
  , (2, MetaBool <$> arbitrary)
  , (3, MetaInlines <$> resize 3 arbitrary)
  , (2, MetaBlocks <$> resize 2 arbitrary)
  ] ++ if n <= 0 then [] else
  [ (2, MetaList <$> resize 3 (listOf (metaValue (n - 1))))
  , (2, MetaMap . M.fromList <$> resize 3 (listOf ((,) <$> key <*> metaValue (n - 1))))
  ]

key :: Gen T.Text
key = T.pack <$> (choose (1, 8) >>= (`vectorOf` elements ['a' .. 'z']))

text :: Gen T.Text
text = T.pack <$> resize 8 (listOf (elements (['a' .. 'z'] ++ " -\"\\\1234")))
