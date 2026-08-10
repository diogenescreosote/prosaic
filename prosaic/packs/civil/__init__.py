"""The general civil California pack: six Judicial Council forms.

Form modules carry the field knowledge; this registry assembles them into
a pack the CLI and agent layer can enumerate and render.
"""

from prosaic.forms.pack import FormPack, define_form
from prosaic.packs.civil import cm010, cm110, mc030, mc031, pos010, sum100
from prosaic.packs.civil.cm010 import CoverSheetContext
from prosaic.packs.civil.cm110 import CaseManagementContext
from prosaic.packs.civil.mc030 import DeclarationContext
from prosaic.packs.civil.pos010 import ProofOfServiceContext
from prosaic.packs.civil.sum100 import SummonsContext

_PACKAGE = "prosaic.packs.civil"

CIVIL_PACK = FormPack(
    name="california-civil",
    jurisdiction="California superior courts, general civil",
    forms=(
        define_form(
            number=cm010.NUMBER,
            title=cm010.TITLE,
            package=_PACKAGE,
            resource="blanks/cm010.pdf",
            context_type=CoverSheetContext,
            build=cm010.build_values,
        ),
        define_form(
            number=cm110.NUMBER,
            title=cm110.TITLE,
            package=_PACKAGE,
            resource="blanks/cm110.pdf",
            context_type=CaseManagementContext,
            build=cm110.build_values,
        ),
        define_form(
            number=sum100.NUMBER,
            title=sum100.TITLE,
            package=_PACKAGE,
            resource="blanks/sum100.pdf",
            context_type=SummonsContext,
            build=sum100.build_values,
        ),
        define_form(
            number=pos010.NUMBER,
            title=pos010.TITLE,
            package=_PACKAGE,
            resource="blanks/pos010.pdf",
            context_type=ProofOfServiceContext,
            build=pos010.build_values,
        ),
        define_form(
            number=mc030.NUMBER,
            title=mc030.TITLE,
            package=_PACKAGE,
            resource="blanks/mc030.pdf",
            context_type=DeclarationContext,
            build=mc030.build_values,
        ),
        define_form(
            number=mc031.NUMBER,
            title=mc031.TITLE,
            package=_PACKAGE,
            resource="blanks/mc031.pdf",
            context_type=DeclarationContext,
            build=mc031.build_values,
        ),
    ),
)

__all__ = ["CIVIL_PACK"]
